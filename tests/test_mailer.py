import base64
import email
import json
import logging
from dataclasses import replace

import httpx
import pytest

from app import mailer
from app.config import Settings

BASE = Settings("gate", "secret", "admin", "neo4j://x", "neo4j", "pw", app_env="production",
                site_url="https://record.example", mail_from="John Kintree <john@example.org>",
                gmail_client_id="client-id", gmail_client_secret="CLIENT-SECRET",
                gmail_refresh_token="REFRESH-TOKEN")
BODY = "Hello Bob,\n\nhttps://record.example/accept/SECRETLINK\n"


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(mailer, "_token", {"value": None, "expires": 0.0})
    monkeypatch.setattr(mailer, "last_mail_error", None)
    monkeypatch.setattr("app.config.get_settings", lambda: BASE)
    monkeypatch.setattr(logging.getLogger("oci"), "propagate", True)


def google(token_status=200, send_status=200, seen=None):
    seen = seen if seen is not None else []

    def respond(request):
        seen.append(request)
        if str(request.url) == mailer.TOKEN_URL:
            if token_status != 200:
                return httpx.Response(token_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "ACCESS", "expires_in": 3599})
        assert str(request.url) == mailer.SEND_URL
        return httpx.Response(send_status, json={"id": "sent-id"})
    return httpx.MockTransport(respond), seen


def test_a_message_goes_through_the_gmail_api_as_plain_text():
    transport, seen = google()
    assert mailer.send("bob@example.org", "Your invitation", BODY, transport=transport) is True
    token, sent = seen
    assert dict(httpx.QueryParams(token.content.decode())) == {
        "grant_type": "refresh_token", "client_id": "client-id",
        "client_secret": "CLIENT-SECRET", "refresh_token": "REFRESH-TOKEN"}
    assert sent.headers["authorization"] == "Bearer ACCESS"
    raw = base64.urlsafe_b64decode(json.loads(sent.content)["raw"])
    message = email.message_from_bytes(raw)
    assert message["From"] == "John Kintree <john@example.org>"
    assert message["To"] == "bob@example.org" and message["Subject"] == "Your invitation"
    assert message.get_content_type() == "text/plain"
    assert message.get_payload(decode=True).decode() == BODY


def test_the_access_token_is_reused_until_it_expires():
    transport, seen = google()
    mailer.send("a@example.org", "One", "x", transport=transport)
    mailer.send("b@example.org", "Two", "y", transport=transport)
    assert [str(r.url) for r in seen].count(mailer.TOKEN_URL) == 1


def test_a_refused_permission_fails_cleanly_and_is_remembered(caplog):
    caplog.set_level(logging.DEBUG, logger="oci")
    transport, _ = google(token_status=400)
    assert mailer.send("bob@example.org", "Your invitation", BODY, request_id="req-1", transport=transport) is False
    assert mailer.last_mail_error["http"] == 400 and mailer.last_mail_error["time"]
    for secret in ("SECRETLINK", "REFRESH-TOKEN", "CLIENT-SECRET", "ACCESS", "Hello Bob"):
        assert secret not in caplog.text
    assert '"request_id": "req-1"' in caplog.text


@pytest.mark.parametrize("send_status", [401, 429, 500])
def test_a_refused_send_returns_false(send_status):
    transport, _ = google(send_status=send_status)
    assert mailer.send("bob@example.org", "S", "T", transport=transport) is False
    assert mailer.last_mail_error["http"] == send_status


def test_a_401_forgets_the_access_token_so_the_next_send_asks_again():
    transport, seen = google(send_status=401)
    mailer.send("bob@example.org", "S", "T", transport=transport)
    assert mailer._token["value"] is None


def test_no_network_returns_false():
    def down(request):
        raise httpx.ConnectError("offline", request=request)
    assert mailer.send("bob@example.org", "S", "T", transport=httpx.MockTransport(down)) is False


def test_an_unexpected_error_is_a_failed_send(caplog):
    """Item 21 of the 5 October review: the entry has committed by now, so any error is a failed
    send the page can offer to retry, never a 500."""
    caplog.set_level(logging.DEBUG, logger="oci")

    def broken(request):
        raise RuntimeError("something odd")
    assert mailer.send("bob@example.org", "S", BODY, transport=httpx.MockTransport(broken)) is False
    assert mailer.last_mail_error["http"] is None and mailer.last_mail_error["time"]
    assert "SECRETLINK" not in caplog.text and "Hello Bob" not in caplog.text


def test_unconfigured_sends_nothing(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: replace(BASE, gmail_refresh_token=None))
    transport, seen = google()
    assert mailer.send("bob@example.org", "S", "T", transport=transport) is False
    assert seen == [] and mailer.last_mail_error["http"] is None


def test_unconfigured_on_the_live_site_warns_and_is_remembered(monkeypatch, caplog):
    """Item 11: accounts switched on without MAIL_FROM or a Gmail variable fails every send; the
    log says so at WARNING (not DEBUG), and the back room line (sub-plan F) shows it."""
    caplog.set_level(logging.DEBUG, logger="oci")
    monkeypatch.setattr("app.config.get_settings", lambda: replace(BASE, mail_from=None, accounts_enabled=True))
    assert mailer.send("bob@example.org", "S", BODY, request_id="req-2") is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings and '"status": "unconfigured"' in warnings[0].getMessage()
    assert mailer.last_mail_error is not None and "SECRETLINK" not in caplog.text


def test_the_console_switch_prints_locally_and_never_in_production(monkeypatch, capsys):
    unconfigured = replace(BASE, gmail_refresh_token=None, mail_console=True)
    monkeypatch.setattr("app.config.get_settings", lambda: unconfigured)
    assert mailer.send("bob@example.org", "S", "local body", transport=google()[0]) is False
    assert "local body" not in capsys.readouterr().out
    monkeypatch.setattr("app.config.get_settings", lambda: replace(unconfigured, app_env="local"))
    assert mailer.send("bob@example.org", "S", "local body", transport=google()[0]) is True
    assert "local body" in capsys.readouterr().out
