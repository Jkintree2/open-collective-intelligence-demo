"""Who is reading. With ACCOUNTS_ENABLED a signed-in account; otherwise the passphrase gate."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import Response

from app import accounts, config, graph_accounts
from app.auth import GATE_COOKIE, GateRequired, check_gate_token

# Client facing copy, word for word from docs/planning/04_interface.md.
SIGN_IN_AGAIN = "Please sign in again."
RELOAD_AND_RETRY = "Please reload the page and try again."

_UNREAD = object()


@dataclass(frozen=True)
class Member:
    key: str
    name: str
    email: str
    admin: bool


class CrossSite(Exception):
    """Raised by require_same_origin; main.py answers with RELOAD_AND_RETRY, never FastAPI's JSON."""


def wants_json(request: Request) -> bool:
    """The card's calls (/api/...) and page scripts that ask for JSON (stances.js) read JSON answers."""
    return request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", "")


def safe_next(next_path: str | None) -> str:
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/"


def _next_path(request: Request) -> str:
    if request.method != "GET":
        return "/"
    return request.url.path + ("?" + request.url.query if request.url.query else "")


def current_member(request: Request) -> Member | None:
    """The account the member cookie names, read once per request. None when accounts are off."""
    cached = getattr(request.state, "member", _UNREAD)
    if cached is not _UNREAD:
        return cached
    found = None
    settings = config.get_settings()
    cookie = request.cookies.get(accounts.MEMBER_COOKIE)
    key = accounts.member_cookie_key(cookie) if settings.accounts_enabled else None
    if key:
        row = graph_accounts.member(key)
        if row and accounts.member_cookie_valid(cookie, row["password_hash"], settings.secret_key):
            found = Member(row["key"], row["name"], row["email"], bool(row["admin"]))
    request.state.member = found
    return found


def member_key(request: Request) -> str | None:
    """The signed-in account's key, or None. Pages pass it to reads as `me`; it never reaches a template."""
    member = current_member(request)
    return member.key if member else None


def require_access(request: Request) -> None:
    """The door of every reading page: an account when accounts are on, the passphrase otherwise."""
    if config.get_settings().accounts_enabled:
        if current_member(request) is not None:
            return
    elif check_gate_token(request.cookies.get(GATE_COOKIE)):
        return
    raise GateRequired(_next_path(request))


def require_member(request: Request) -> Member:
    """Pages that exist only with accounts (entering people, stances, own posts, tidying)."""
    if not config.get_settings().accounts_enabled:
        raise HTTPException(404)
    member = current_member(request)
    if member is None:
        raise GateRequired(_next_path(request))
    return member


def require_same_origin(request: Request) -> None:
    """Writes are posted from this site only. SameSite=Lax already keeps the cookie off a form
    posted from another site; this refuses such posts outright. Origin first, then Referer when a
    browser leaves Origin out, as the back room does (auth.require_admin_mutation)."""
    site = request.headers.get("sec-fetch-site")
    if site == "same-origin":  # set by the browser itself; a page cannot forge it
        return
    if site == "cross-site":
        raise CrossSite()
    source = request.headers.get("origin") or request.headers.get("referer")
    if source is None:
        return
    try:
        parts = urlsplit(source)
    except ValueError:
        raise CrossSite()
    # Hosts only: behind Render's proxy the request reads as http while the browser says https.
    if parts.scheme not in ("http", "https") or parts.netloc != request.url.netloc:
        raise CrossSite()


def set_member_cookie(response: Response, key: str, password_hash: str) -> None:
    settings = config.get_settings()
    response.set_cookie(accounts.MEMBER_COOKIE,
                        accounts.make_member_cookie(key, password_hash, settings.secret_key),
                        max_age=accounts.MEMBER_SECONDS, httponly=True, samesite="lax",
                        secure=not settings.is_local)


def clear_member_cookie(response: Response) -> None:
    response.delete_cookie(accounts.MEMBER_COOKIE, httponly=True, samesite="lax",
                           secure=not config.get_settings().is_local)
