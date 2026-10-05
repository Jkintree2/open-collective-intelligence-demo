"""Email from John's own Gmail through the Gmail API, with the send permission only (D1).

One function, send(), so a platform address can replace it later. Nothing here logs a message,
a link, the refresh token or the client secret; log lines carry the request id, status and time.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

import httpx

from app import config

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

log = logging.getLogger("oci")
# The last failure of any kind, unconfigured included, for the back room's "Sending email" line
# (sub-plan F). Cleared by a restart.
last_mail_error: dict[str, Any] | None = None
_token: dict[str, Any] = {"value": None, "expires": 0.0}
_lock = threading.Lock()


def _configured(settings: config.Settings) -> bool:
    return bool(settings.mail_from and settings.gmail_client_id and settings.gmail_client_secret
                and settings.gmail_refresh_token)


def _raw(settings: config.Settings, to: str, subject: str, text: str) -> str:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def _access_token(client: httpx.Client, settings: config.Settings) -> str:
    with _lock:
        if _token["value"] and _token["expires"] > time.monotonic() + 60:
            return _token["value"]
    response = client.post(TOKEN_URL, data={
        "grant_type": "refresh_token", "client_id": settings.gmail_client_id,
        "client_secret": settings.gmail_client_secret, "refresh_token": settings.gmail_refresh_token})
    response.raise_for_status()
    body = response.json()
    with _lock:
        _token.update(value=body["access_token"], expires=time.monotonic() + float(body.get("expires_in", 3600)))
    return body["access_token"]


def _remember(http: int | None) -> None:
    global last_mail_error
    last_mail_error = {"time": datetime.now(timezone.utc).isoformat(), "http": http}


def send(to: str, subject: str, text: str, *, request_id: str | None = None,
         transport: httpx.BaseTransport | None = None) -> bool:
    """True when Gmail accepted the message. Any failure is False, logged without content; this
    function never raises, because callers send after the record has changed."""
    settings = config.get_settings()
    if not _configured(settings):
        if settings.is_local and settings.mail_console:
            # Local checks only: shows the link on the developer's terminal. Never in production.
            print(f"--- email to {to} ---\nSubject: {subject}\n\n{text}", flush=True)
            return True
        # On the live site with accounts on this is a mistake in Render's variables (MAIL_FROM or a
        # GMAIL_* missing): say so loudly. Locally and in tests it is the normal quiet case.
        loud = settings.accounts_enabled and not settings.is_local
        log.log(logging.WARNING if loud else logging.DEBUG,
                json.dumps({"event": "mail", "request_id": request_id, "status": "unconfigured"}))
        _remember(None)
        return False
    started = time.perf_counter()
    status, http = "ok", None
    try:
        with httpx.Client(timeout=httpx.Timeout(10, connect=5), transport=transport) as client:
            token = _access_token(client, settings)
            response = client.post(SEND_URL, headers={"Authorization": f"Bearer {token}"},
                                   json={"raw": _raw(settings, to, subject, text)})
            http = response.status_code
            if response.status_code == 401:
                with _lock:
                    _token["value"] = None  # revoked or expired early: ask for a new one next time
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status, http = "http", exc.response.status_code
    except Exception:  # noqa: BLE001  any other failure is a failed send; nothing about it is logged but its kind
        status = "error"
    if status != "ok":
        _remember(http)
    log.info(json.dumps({"event": "mail", "request_id": request_id, "status": status, "http": http,
                         "ms": round((time.perf_counter() - started) * 1000)}))
    return status == "ok"
