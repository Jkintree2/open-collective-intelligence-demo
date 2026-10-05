"""The back room's People section (sub-plan F): every account and what John can do for it.

HTTP Basic auth like the rest of /admin, and only with ACCOUNTS_ENABLED. Rows come from Q20's back
room version; the link fields only decide a row's state and never reach the template. Names and
addresses stay on the page: notices travel as ?done=<word>, and log lines carry no names.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app import accounts, graph_accounts
from app.auth import require_admin
from app.routes_accounts import accounts_on

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
