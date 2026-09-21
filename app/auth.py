"""The passphrase gate: one signed cookie, no session store (PLAN_v2 decision 6)."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time

from fastapi import Depends, Form, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from urllib.parse import urlsplit
import secrets

from app.config import get_settings

GATE_COOKIE = "oci_pass"
GATE_DAYS = 30
GATE_SECONDS = GATE_DAYS * 86400
WRONG_PASSPHRASE_DELAY = 1.0


def _signature(expiry: int, secret_key: str, passphrase: str) -> str:
    passphrase_hash = hashlib.sha256(passphrase.encode("utf-8")).hexdigest()
    message = f"{expiry}:{passphrase_hash}".encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _resolve(secret_key: str | None, passphrase: str | None) -> tuple[str, str]:
    if secret_key is None or passphrase is None:
        settings = get_settings()
        secret_key = secret_key if secret_key is not None else settings.secret_key
        passphrase = passphrase if passphrase is not None else settings.demo_passphrase
    return secret_key, passphrase


def make_gate_token(
    now: float | None = None, *, secret_key: str | None = None, passphrase: str | None = None
) -> str:
    """`"{expiry}.{hmac}"`, valid for thirty days from `now`."""
    secret_key, passphrase = _resolve(secret_key, passphrase)
    expiry = int((time.time() if now is None else now) + GATE_SECONDS)
    return f"{expiry}.{_signature(expiry, secret_key, passphrase)}"


def check_gate_token(
    token: str | None,
    now: float | None = None,
    *,
    secret_key: str | None = None,
    passphrase: str | None = None,
) -> bool:
    """True when the token is well formed, unexpired and signed under the current passphrase."""
    if not token or "." not in token:
        return False
    expiry_text, signature = token.split(".", 1)
    if not expiry_text.isdigit() or not signature:
        return False
    expiry = int(expiry_text)
    if expiry <= (time.time() if now is None else now):
        return False
    secret_key, passphrase = _resolve(secret_key, passphrase)
    return hmac.compare_digest(signature, _signature(expiry, secret_key, passphrase))


def passphrase_matches(given: str, *, passphrase: str | None = None) -> bool:
    _, passphrase = _resolve("", passphrase)
    return hmac.compare_digest(given.encode("utf-8"), passphrase.encode("utf-8"))


class GateRequired(Exception):
    """Raised by `require_gate`; the app turns it into a redirect to /enter."""

    def __init__(self, next_path: str) -> None:
        super().__init__(next_path)
        self.next_path = next_path


def require_gate(request: Request) -> None:
    """FastAPI dependency: the gate cookie must be present and valid."""
    if check_gate_token(request.cookies.get(GATE_COOKIE)):
        return
    if request.method == "GET":
        next_path = request.url.path
        if request.url.query:
            next_path += "?" + request.url.query
    else:
        next_path = "/"
    raise GateRequired(next_path)


class MinuteBucket:
    """A token bucket held in this process only: `capacity` tokens, refilled over `period` seconds."""

    def __init__(self, capacity: int = 6, period: float = 60.0) -> None:
        self.capacity = capacity
        self.period = period
        self.tokens = float(capacity)
        self.updated: float | None = None
        self._lock = threading.Lock()

    def _refill(self, now: float) -> None:
        if self.updated is not None:
            elapsed = max(0.0, now - self.updated)
            self.tokens = min(float(self.capacity), self.tokens + elapsed * self.capacity / self.period)
        self.updated = now

    def take(self, now: float | None = None) -> bool:
        """Spend one token; False when the bucket is empty."""
        with self._lock:
            self._refill(time.monotonic() if now is None else now)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False

    def has_token(self, now: float | None = None) -> bool:
        with self._lock:
            self._refill(time.monotonic() if now is None else now)
            return self.tokens >= 1.0


# Failed passphrase attempts draw from this bucket. Session 3 shares it with the reading service.
attempt_bucket = MinuteBucket(capacity=6, period=60.0)


class DailyLimit:
    def __init__(self, capacity: int = 300) -> None:
        self.capacity = capacity
        self.day: int | None = None
        self.used = 0
        self.lock = threading.Lock()

    def take(self, minute: MinuteBucket, now: float | None = None) -> bool:
        today = int((time.time() if now is None else now) // 86400)
        with self.lock:
            if self.day != today:
                self.day, self.used = today, 0
            if self.used >= self.capacity or not minute.take():
                return False
            self.used += 1
            return True


reading_limit = DailyLimit()


class PostSpacing:
    """One post per source per `seconds`, held in this process; old entries are swept."""

    def __init__(self, seconds: float = 20.0) -> None:
        self.seconds = seconds
        self.last: dict[str, float] = {}
        self._lock = threading.Lock()

    def take(self, source_key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            for key, then in list(self.last.items()):
                if now - then >= self.seconds:
                    del self.last[key]
            if source_key in self.last:
                return False
            self.last[source_key] = now
            return True


post_spacing = PostSpacing()

admin_basic = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(admin_basic)) -> None:
    if not hmac.compare_digest(credentials.password.encode(), get_settings().admin_token.encode()):
        raise HTTPException(401, "Password required", headers={"WWW-Authenticate": "Basic"})


def _admin_signature(value: str) -> str:
    settings = get_settings()
    message = f"admin:{settings.admin_token}:{value}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def make_admin_csrf() -> str:
    value = f"{int(time.time()) + 3600}.{secrets.token_hex(16)}"
    return f"{value}.{_admin_signature(value)}"


def require_admin_mutation(request: Request, csrf_token: str = Form(""),
                           _: None = Depends(require_admin)) -> None:
    """Basic auth is attached automatically, so mutations also need form proof."""
    try:
        expiry, nonce, signature = csrf_token.split(".")
        valid = (len(expiry) <= 12 and expiry.isascii() and expiry.isdigit()
                 and int(expiry) > time.time() and len(nonce) == 32
                 and hmac.compare_digest(signature, _admin_signature(f"{expiry}.{nonce}")))
    except (ValueError, TypeError):
        valid = False
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    # Hosts only. Behind a proxy that ends TLS this request reads as http while the browser
    # sends https, so comparing schemes would refuse every real mutation; the signed token
    # above is what proves the form came from the back room.
    expected = request.url.netloc
    try:
        if origin:
            parsed = urlsplit(origin)
            valid = valid and parsed.scheme in ("http", "https") and parsed.netloc == expected and not parsed.path
        elif referer:
            parsed = urlsplit(referer)
            valid = valid and parsed.scheme in ("http", "https") and parsed.netloc == expected
    except ValueError:
        valid = False
    if request.headers.get("sec-fetch-site") == "cross-site":
        valid = False
    if not valid:
        raise HTTPException(403, "Please open the back room again and retry.")
