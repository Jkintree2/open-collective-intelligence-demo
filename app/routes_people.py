"""Entering a person, sending the invitation again, withdrawing, and accepting (sub-plan B)."""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response

from app import accounts, config, emails, graph_accounts, mailer
from app.auth import TOO_MANY_TRIES
from app.graph_accounts import EmailTaken
from app.members import Member, require_member, require_same_origin
from app.pages import page
from app.text import make_key

log = logging.getLogger("oci")
router = APIRouter()

# Client facing copy, word for word from docs/planning/04_interface.md.
ENTERED_OK = "{name} is entered. The invitation is on its way to {email}. The link works for 14 days."
ENTERED_NO_EMAIL = "{name} is entered, but the invitation email did not go. Please try again in a minute."
ENTERED_ALREADY = "{name} is entered. If the invitation does not arrive, use Send the invitation again in the list below."
FILL_EVERY_FIELD = "Please fill in every field."
TICK_AGREED = "Please enter only someone who has agreed, and tick the box to say so."
EMAIL_INCOMPLETE = "That email address does not look complete. Please check it."
ALREADY_ENTERED = "Someone with that email address has already been entered."
TOO_MANY_TO_ADDRESS = "Too many emails to that address in the last hour. Please try again later."
RESENT = "A new invitation is on its way to {email}. The earlier link no longer works."
WITHDRAWN = "The entry for {name} is withdrawn."

DOUBLE_TAP_SECONDS = 60


def _field(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


def _people_page(request: Request, member: Member, *, notice: str | None = None, message: str | None = None,
                 form: dict | None = None, failed_key: str | None = None, rows: list[dict] | None = None,
                 status_code: int = 200) -> Response:
    now = datetime.now(timezone.utc)
    rows = graph_accounts.entered_by(member.key) if rows is None else rows
    # Only what the list shows: no email, link purpose or expiry reaches the template.
    entries = [{"key": row["key"], "name": row["name"], "relationship": row["relationship"],
                "entered_at": row["entered_at"], "accepted_at": row["accepted_at"],
                "state": accounts.entry_state(row, now)} for row in rows]
    return page(request, "people.html", {"entries": entries, "notice": notice, "message": message,
                                         "form": form or {}, "failed_key": failed_key,
                                         "relationships": accounts.RELATIONSHIPS},
                status_code=status_code, private=True)


def _own_unaccepted(member: Member, key: str) -> dict | None:
    """The member's own entry, while it is not accepted; anything else is left alone."""
    for row in graph_accounts.entered_by(member.key):
        if row["key"] == key and row["accepted_at"] is None:
            return row
    return None


def _send_invitation(request: Request, *, email: str, name: str, inviter_name: str | None,
                     relationship: str | None, secret: str) -> bool:
    settings = config.get_settings()
    subject, text = emails.invitation_for(settings.site_name, name, inviter_name, relationship,
                                          accounts.link_url(settings.site_url, "accept", secret))
    return mailer.send(email, subject, text, request_id=getattr(request.state, "request_id", None))


@router.get("/people")
def people(request: Request, entered: str | None = None, resent: str | None = None,
           member: Member = Depends(require_member)) -> Response:
    rows = graph_accounts.entered_by(member.key)
    notice = None
    for row in rows:
        if row["key"] == entered and row["accepted_at"] is None:
            notice = ENTERED_OK.format(name=row["name"], email=row["email"])
        elif row["key"] == resent and row["accepted_at"] is None:
            notice = RESENT.format(email=row["email"])
    return _people_page(request, member, notice=notice, rows=rows)


@router.post("/people", dependencies=[Depends(require_same_origin)])
def enter(request: Request, name: str = Form(""), email: str = Form(""), country: str = Form(""),
          postal_code: str = Form(""), relationship: str = Form(""), agreed: str = Form(""),
          member: Member = Depends(require_member)) -> Response:
    form = {"name": accounts.person_name(name), "email": accounts.normalise_email(email),
            "country": _field(country, 80), "postal_code": _field(postal_code, 20), "relationship": relationship}
    if (not all(form.values()) or make_key(form["name"]) is None
            or relationship not in accounts.RELATIONSHIPS):
        return _people_page(request, member, message=FILL_EVERY_FIELD, form=form)
    if not agreed:
        return _people_page(request, member, message=TICK_AGREED, form=form)
    if not accounts.looks_like_email(form["email"]):
        return _people_page(request, member, message=EMAIL_INCOMPLETE, form=form)
    if not accounts.entering_limit.take(member.key):
        return _people_page(request, member, message=TOO_MANY_TRIES, form=form, status_code=429)
    now = datetime.now(timezone.utc)
    secret, token_hash = accounts.new_link()
    key = f"acct:{uuid.uuid4()}"
    try:
        allowed = graph_accounts.enter_person(
            inviter_key=member.key, key=key, name=form["name"], email=form["email"], country=form["country"],
            postal_code=form["postal_code"], relationship=relationship, token_hash=token_hash,
            expires_at=accounts.link_expiry("invite", now), now=now)
    except EmailTaken:
        # The same member, the same address, a moment ago: the first tap did it. Its email may have
        # failed, so this answer promises nothing; the list's state and button tell the truth.
        if graph_accounts.recent_entry(member.key, form["email"], now - timedelta(seconds=DOUBLE_TAP_SECONDS)):
            return _people_page(request, member, notice=ENTERED_ALREADY.format(name=form["name"]))
        return _people_page(request, member, message=ALREADY_ENTERED, form=form)
    if not allowed:  # switched off a moment ago: the next page sends the member to sign in
        return RedirectResponse("/people", status_code=303)
    sent = _send_invitation(request, email=form["email"], name=form["name"], inviter_name=member.name,
                            relationship=relationship, secret=secret)
    log.info(json.dumps({"event": "entered", "request_id": getattr(request.state, "request_id", None),
                         "sent": sent}))
    if sent:
        return RedirectResponse(f"/people?entered={quote(key, safe='')}", status_code=303)
    return _people_page(request, member, message=ENTERED_NO_EMAIL.format(name=form["name"]), failed_key=key)


@router.post("/people/{key}/resend", dependencies=[Depends(require_same_origin)])
def resend(request: Request, key: str, member: Member = Depends(require_member)) -> Response:
    entry = _own_unaccepted(member, key)
    if entry is None:  # someone else's, accepted meanwhile, or withdrawn
        return RedirectResponse("/people", status_code=303)
    if not accounts.entering_limit.take(member.key):
        return _people_page(request, member, message=TOO_MANY_TRIES, status_code=429)
    if not accounts.link_per_address.take(entry["email"]):
        return _people_page(request, member, message=TOO_MANY_TO_ADDRESS, status_code=429)
    secret, token_hash = accounts.new_link()
    row = graph_accounts.resend_invitation(key, token_hash, accounts.link_expiry("invite", datetime.now(timezone.utc)),
                                           inviter_key=member.key)
    if row is None:  # accepted or withdrawn a moment ago
        return RedirectResponse("/people", status_code=303)
    if _send_invitation(request, email=row["email"], name=row["name"], inviter_name=row["inviter_name"],
                        relationship=row["relationship"], secret=secret):
        return RedirectResponse(f"/people?resent={quote(key, safe='')}", status_code=303)
    return _people_page(request, member, message=ENTERED_NO_EMAIL.format(name=row["name"]), failed_key=key)


@router.get("/people/{key}/withdraw")
def withdraw_confirm(request: Request, key: str, member: Member = Depends(require_member)) -> Response:
    entry = _own_unaccepted(member, key)
    if entry is None:
        return RedirectResponse("/people", status_code=303)
    return page(request, "withdraw.html", {"entry": {"key": entry["key"], "name": entry["name"]}}, private=True)


@router.post("/people/{key}/withdraw", dependencies=[Depends(require_same_origin)])
def withdraw(request: Request, key: str, member: Member = Depends(require_member)) -> Response:
    entry = _own_unaccepted(member, key)
    # Someone else's, accepted meanwhile, or withdrawn already (a refresh of this answer): nothing to do.
    if entry is None or not graph_accounts.withdraw(key, inviter_key=member.key):
        return RedirectResponse("/people", status_code=303)
    return _people_page(request, member, notice=WITHDRAWN.format(name=entry["name"]))
