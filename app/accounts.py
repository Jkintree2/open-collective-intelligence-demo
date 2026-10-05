"""Accounts without a session store: emails, passwords, emailed links and the member cookie.

03_schema.md, "Phase 1: people and positions". No I/O here; the record is read by graph_accounts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
from datetime import datetime, timedelta

from app.auth import KeyedLimit, MinuteBucket

MIN_PASSWORD = 10
INVITE_DAYS = 14
RESET_HOURS = 1
MEMBER_COOKIE = "oci_member"
MEMBER_DAYS = 30
MEMBER_SECONDS = MEMBER_DAYS * 86400
RELATIONSHIPS = ("family", "neighbor", "friend", "work", "school", "health", "organization")

# Client facing copy, word for word from docs/planning/04_interface.md.
PASSWORD_TOO_SHORT = "Please use at least 10 characters for your password."
PASSWORDS_DIFFER = "The two passwords are not the same."

# Limits held in this process, read as accounts.<name> at call time so a test can swap them.
# Sign in: every attempt on the site, then every attempt for one address, both taken before the
# password is checked (a flood of attempts must not run scrypt). "Too many tries. Please wait a
# minute" is true of both: their windows are a minute.
sign_in_per_minute = MinuteBucket(capacity=20, period=60)
sign_in_per_address = KeyedLimit(5, 60)

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
# Each scrypt run takes 16 MiB and real CPU; Render's free instance has 512 MB and 0.1 CPU, and
# FastAPI runs up to 40 requests at once. Two at a time, the rest wait their turn.
_SCRYPT_SLOTS = threading.BoundedSemaphore(2)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    with _SCRYPT_SLOTS:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen)


def normalise_email(value: str) -> str:
    return value.strip().lower()


def looks_like_email(value: str) -> bool:
    """A loose check that catches typing slips; the invitation email is the real test."""
    return len(value) <= 254 and bool(_EMAIL.match(value))


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """`scrypt$n$r$p$salt$hash`, a fresh 16 byte salt each time."""
    salt = salt or secrets.token_bytes(16)
    digest = _scrypt(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P, 32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def check_password(password: str, stored: str | None) -> bool:
    """False for a missing or malformed hash; the digests are compared in constant time."""
    try:
        scheme, n, r, p, salt, digest = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest, validate=True)
        actual = _scrypt(password, base64.b64decode(salt, validate=True), int(n), int(r), int(p),
                         len(expected) or 1)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def password_problem(password: str, again: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return PASSWORD_TOO_SHORT
    if not hmac.compare_digest(password.encode("utf-8"), again.encode("utf-8")):
        return PASSWORDS_DIFFER
    return None


def link_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def new_link() -> tuple[str, str]:
    """A fresh secret for the email, and the hash that is all the record keeps."""
    secret = secrets.token_urlsafe(32)
    return secret, link_hash(secret)


def link_expiry(purpose: str, now: datetime) -> datetime:
    return now + (timedelta(days=INVITE_DAYS) if purpose == "invite" else timedelta(hours=RESET_HOURS))


def link_state(row: dict | None, purpose: str, now: datetime) -> str:
    """'ok', 'expired' or 'gone' for a Q15 row opened on the `purpose` page. Used, replaced,
    withdrawn and unknown links all read as 'gone': the record cannot tell them apart."""
    if row is None or row.get("purpose") != purpose or not row.get("active"):
        return "gone"
    if row["expires_at"] <= now:
        return "expired"
    return "ok"


def _member_signature(key: str, expiry: int, password_hash: str, secret_key: str) -> str:
    fingerprint = hashlib.sha256(password_hash.encode("utf-8")).hexdigest()
    message = f"member:{key}:{expiry}:{fingerprint}".encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def make_member_cookie(key: str, password_hash: str, secret_key: str, now: float | None = None) -> str:
    """`key.expiry.signature`; a new password hash makes every older cookie stop working."""
    expiry = int((time.time() if now is None else now) + MEMBER_SECONDS)
    return f"{key}.{expiry}.{_member_signature(key, expiry, password_hash, secret_key)}"


def member_cookie_key(cookie: str | None, now: float | None = None) -> str | None:
    """The account a well formed, unexpired cookie names. The signature is checked afterwards,
    against the password hash the record holds (`member_cookie_valid`)."""
    parts = (cookie or "").split(".")
    if len(parts) != 3:
        return None
    key, expiry, signature = parts
    if not key.startswith("acct:") or not (expiry.isascii() and expiry.isdigit()) or len(signature) != 64:
        return None
    if int(expiry) <= (time.time() if now is None else now):
        return None
    return key


def member_cookie_valid(cookie: str, password_hash: str | None, secret_key: str) -> bool:
    if not password_hash or member_cookie_key(cookie) is None:
        return False
    key, expiry, signature = cookie.split(".")
    if not signature.isascii():  # compare_digest raises on non-ASCII text; a forged cookie must just fail
        return False
    return hmac.compare_digest(signature, _member_signature(key, int(expiry), password_hash, secret_key))
