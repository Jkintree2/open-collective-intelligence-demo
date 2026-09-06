"""The passphrase gate: one signed cookie, no session store (PLAN_v2 decision 6)."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time

from fastapi import Request

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
