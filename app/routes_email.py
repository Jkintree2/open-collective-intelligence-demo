"""X2: changing one's email (03_schema.md and 04_interface.md, "Change of email"). Nothing changes until the
link sent to the new address is opened; every earlier address stays on the account with its date."""

import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import Response

from app import accounts, config, emails, graph_accounts, mailer
from app.auth import TOO_MANY_TRIES, WRONG_PASSPHRASE_DELAY
from app.members import Member, current_member, require_member, require_same_origin
from app.pages import link_problem, page
from app.routes_accounts import NOT_CURRENT, _account_page, accounts_on, too_many_tries

log = logging.getLogger("oci")
router = APIRouter()

# Client facing copy, word for word from docs/planning/04_interface.md.
NOT_AN_EMAIL = "Please enter an email address."
ALREADY_YOURS = "That is already your email."
TAKEN_MEANWHILE = "That address is now used by another account. Your email has not changed."


def link_sent(new: str, current: str) -> str:
    return (f"We have sent a link to {new}. Open it to finish the change. If it does not arrive in a few minutes, "
            f"please check your spam folder. Until then, sign in with {current}.")


def email_change_on() -> None:
    """X2 has its own switch, EMAIL_CHANGE_ENABLED, so it can wait for John's yes on the wording while the
    rest goes live; unset, these pages do not exist (and they never do without accounts)."""
    accounts_on()
    if not config.get_settings().email_change_enabled:
        raise HTTPException(404)


@router.post("/account/email", dependencies=[Depends(email_change_on), Depends(require_same_origin)])
def ask(request: Request, background: BackgroundTasks, email: str = Form(""), current: str = Form(""),
        member: Member = Depends(require_member)) -> Response:
    # The same limits and order as changing the password: no scrypt once a bucket is empty.
    if too_many_tries(member.email):
        return _account_page(request, member, email_message=TOO_MANY_TRIES, status_code=429)
    row = graph_accounts.member(member.key)
    if not row or not accounts.check_password(current, row["password_hash"]):
        time.sleep(WRONG_PASSPHRASE_DELAY)
        return _account_page(request, member, email_message=NOT_CURRENT)
    new = accounts.normalise_email(email)
    if not accounts.looks_like_email(new):
        return _account_page(request, member, email_message=NOT_AN_EMAIL)
    if new == member.email:
        return _account_page(request, member, email_message=ALREADY_YOURS)
    # Every address gets the same answer: whether it can be used is decided after the answer has gone,
    # and a busy address is quietly skipped, as on "Forgot your password?".
    if accounts.email_change_per_account.take(member.key) and accounts.link_per_address.take(new):
        background.add_task(_send_link, getattr(request.state, "request_id", None), member.key, new)
    return _account_page(request, member, notice=link_sent(new, member.email))


def _send_link(request_id: str | None, key: str, new: str) -> None:
    """The link to the new address and a note to the old one. Logged without addresses or links."""
    settings = config.get_settings()
    secret, token_hash = accounts.new_link()
    try:
        row = graph_accounts.ask_email_change(key, new, token_hash,
                                              accounts.link_expiry("email", datetime.now(timezone.utc)))
    except Exception as exc:  # noqa: BLE001  the page has answered
        log.warning(json.dumps({"event": "email_change_failed", "request_id": request_id, "error": type(exc).__name__}))
        return
    if row is None:
        log.info(json.dumps({"event": "email_change_refused", "request_id": request_id}))
        return
    subject, text = emails.email_change_link(settings.site_name, row["name"],
                                             accounts.link_url(settings.site_url, "email", secret))
    mailer.send(new, subject, text, request_id=request_id)
    subject, text = emails.email_change_notice(settings.site_name, row["name"], new)
    mailer.send(row["email"], subject, text, request_id=request_id)


def _open(request: Request, secret: str) -> tuple[dict | None, Response | None]:
    email_change_on()
    here = f"/email/{secret}"
    # As the other link pages: a link longer than any real one is not looked up.
    row = graph_accounts.open_link(accounts.link_hash(secret)) if len(secret) <= 100 else None
    state = accounts.link_state(row, "email", datetime.now(timezone.utc))
    if state != "ok":
        return None, link_problem(request, "expired_email" if state == "expired" else "gone", here=here)
    member = current_member(request)
    if member is not None and member.key != row["key"]:
        return None, link_problem(request, "someone_else", here=here)
    return row, None


@router.get("/email/{secret}")
def confirm_page(request: Request, secret: str) -> Response:
    row, problem = _open(request, secret)
    return problem or page(request, "email_change.html", {"secret": secret, "new": row["pending_email"],
                                                          "old": row["email"]}, private=True)


@router.post("/email/{secret}", dependencies=[Depends(require_same_origin)])
def confirm(request: Request, secret: str) -> Response:
    row, problem = _open(request, secret)
    if problem:
        return problem
    result = graph_accounts.confirm_email_change(accounts.link_hash(secret), datetime.now(timezone.utc))
    if result is None:  # used a moment ago, in another tab
        return link_problem(request, "gone", here=f"/email/{secret}")
    member = current_member(request)
    log.info(json.dumps({"event": "email_changed" if result["free"] else "email_change_taken",
                         "request_id": getattr(request.state, "request_id", None)}))
    return page(request, "email_change.html", {"done": True, "free": result["free"], "new": row["pending_email"],
                                               "message": None if result["free"] else TAKEN_MEANWHILE,
                                               "signed_in": member is not None}, private=True)
