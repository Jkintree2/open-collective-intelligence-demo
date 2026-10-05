"""The back room's People section (sub-plan F): every account and what John can do for it.

HTTP Basic auth like the rest of /admin, and only with ACCOUNTS_ENABLED. Rows come from Q20's back
room version; the link fields only decide a row's state and never reach the template. Names and
addresses stay on the page: notices travel as ?done=<word>, and log lines carry no names.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from app import accounts, config, emails, graph_accounts, mailer
from app.auth import require_admin, require_admin_mutation
from app.routes_accounts import accounts_on

log = logging.getLogger("oci")

router = APIRouter(prefix="/admin/people", dependencies=[Depends(require_admin), Depends(accounts_on)])

# Client facing copy, word for word from docs/planning/04_interface.md ("Back room additions").
NOTICES = {
    "resent": "Invitation sent again.",
    "password_link": "Password link sent.",
    "withdrawn": "Entry withdrawn.",
    "switched_off": "Switched off.",
    "switched_on": "Switched on.",
    "mail_failed": "The email did not go. Please try again in a minute.",
    "address_busy": "Too many emails to that address in the last hour. Please try again later.",
}
# Each plain button: the last part of its address, and its label. Withdraw and Switch off are
# drawn on their own in the template, because they ask first.
BUTTONS = {
    "resend": ("resend", "Send the invitation again"),
    "password_link": ("password-link", "Send a password link"),
    "switch_on": ("switch-on", "Switch on"),
}
SHOWN = ("key", "name", "email", "inviter_name", "relationship", "entered_at", "accepted_at")


def _actions(state: str, first: bool, admin: bool) -> list[str]:
    """The buttons a row offers. John's own account (the first, with nobody who entered it) is
    never withdrawn and never switched off."""
    if state == "switched off":
        return ["switch_on"]
    if state == "joined":
        return ["password_link"] if admin else ["password_link", "switch_off"]
    return ["resend"] if first else ["resend", "withdraw"]


def page_rows() -> list[dict]:
    now = datetime.now(timezone.utc)
    rows = []
    for row in graph_accounts.all_accounts():
        state = accounts.entry_state(row, now)
        first = row["inviter_name"] is None
        rows.append({**{key: row[key] for key in SHOWN}, "state": state, "first": first,
                     "actions": _actions(state, first, bool(row["admin"]))})
    return rows


def _account(key: str, action: str) -> dict | None:
    """The row, if it is still listed and still offers this button. Anything else (accepted,
    withdrawn or switched off meanwhile, or John's own row) changes nothing."""
    row = next((row for row in page_rows() if row["key"] == key), None)
    return row if row is not None and action in row["actions"] else None


def _done(notice: str | None = None) -> Response:
    return RedirectResponse(f"/admin?done={notice}#people" if notice else "/admin#people", status_code=303)


def _limited(email: str) -> str | None:
    """03_schema.md Q17: the same per address limit as "Forgot your password?" and "Send the
    invitation again". No per minute bucket: the back room is behind Basic auth, and anonymous
    posts to /forgot-password must never block John's buttons."""
    if not accounts.link_per_address.take(email):
        return "address_busy"
    return None


def _log(request: Request, action: str, **facts) -> None:
    log.info(json.dumps({"event": "back_room_people", "action": action,
                         "request_id": getattr(request.state, "request_id", None), **facts}))


def _send(request: Request, action: str, to: str, subject: str, text: str, *, done: str) -> str:
    """The notice: `done` when Gmail took the email, otherwise "mail_failed"."""
    sent = mailer.send(to, subject, text, request_id=getattr(request.state, "request_id", None))
    _log(request, action, sent=sent)
    return done if sent else "mail_failed"


@router.post("/{key}/resend", dependencies=[Depends(require_admin_mutation)])
def resend(request: Request, key: str) -> Response:
    row = _account(key, "resend")
    if row is None:
        return _done()
    busy = _limited(row["email"])
    if busy:
        return _done(busy)
    secret, token_hash = accounts.new_link()
    found = graph_accounts.resend_invitation(key, token_hash, accounts.link_expiry("invite", datetime.now(timezone.utc)))
    if found is None:  # accepted or switched off a moment ago
        return _done()
    settings = config.get_settings()
    # B2's one builder for accept links: John's own wording when nobody entered the person (X3).
    subject, text = emails.invitation_for(settings.site_name, found["name"], found["inviter_name"],
                                          found["relationship"], accounts.link_url(settings.site_url, "accept", secret))
    return _done(_send(request, "resend", found["email"], subject, text, done="resent"))


@router.post("/{key}/password-link", dependencies=[Depends(require_admin_mutation)])
def password_link(request: Request, key: str) -> Response:
    row = _account(key, "password_link")
    if row is None:
        return _done()
    busy = _limited(row["email"])
    if busy:
        return _done(busy)
    secret, token_hash = accounts.new_link()
    found = graph_accounts.password_link(key, token_hash, accounts.link_expiry("reset", datetime.now(timezone.utc)))
    if found is None:  # switched off a moment ago
        return _done()
    settings = config.get_settings()
    subject, text = emails.password_link(settings.site_name, found["name"],
                                         accounts.link_url(settings.site_url, "reset", secret))
    return _done(_send(request, "password_link", found["email"], subject, text, done="password_link"))


@router.post("/{key}/withdraw", dependencies=[Depends(require_admin_mutation)])
def withdraw(request: Request, key: str) -> Response:
    if _account(key, "withdraw") is None:
        return _done()
    withdrawn = graph_accounts.withdraw(key)
    _log(request, "withdraw", changed=withdrawn)
    return _done("withdrawn" if withdrawn else None)


def _switch(request: Request, key: str, action: str, active: bool, notice: str) -> Response:
    if _account(key, action) is None:
        return _done()
    changed = graph_accounts.set_active(key, active)
    _log(request, action, changed=changed)
    return _done(notice if changed else None)


@router.post("/{key}/switch-off", dependencies=[Depends(require_admin_mutation)])
def switch_off(request: Request, key: str) -> Response:
    return _switch(request, key, "switch_off", False, "switched_off")


@router.post("/{key}/switch-on", dependencies=[Depends(require_admin_mutation)])
def switch_on(request: Request, key: str) -> Response:
    return _switch(request, key, "switch_on", True, "switched_on")
