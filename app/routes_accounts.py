"""Sign in, sign out, your account, changing the password, and forgotten passwords (sub-plan A)."""

import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import accounts, config, emails, graph_accounts, graph_own_posts, mailer
from app.auth import TOO_MANY_TRIES, WRONG_PASSPHRASE_DELAY
from app.members import (Member, clear_member_cookie, current_member, require_member, require_same_origin,
                         safe_next, set_member_cookie)
from app.pages import link_problem, page
from app.text import make_key

log = logging.getLogger("oci")
router = APIRouter()

# Client facing copy, word for word from docs/planning/04_interface.md.
NOT_MATCHED = "That email and password did not match. Check them and try again."
SIGNED_OUT = "You are signed out."
NOT_CURRENT = "That is not your current password."
PASSWORD_CHANGED = "Your password is changed. You are signed out everywhere else."
DETAILS_SAVED = "Your details are saved."
FILL_IN_NAME_AND_COUNTRY = "Please fill in your name and country."
FORGOT_SENT = "If that address belongs to someone taking part, an email with a link is on its way."

# Checked when the address is unknown, so a stranger's address takes as long as a wrong password.
_NOBODY = accounts.hash_password("no account has this password")


def accounts_on() -> None:
    """Pages that exist only with accounts; sub-plan B's acceptance page uses it too."""
    if not config.get_settings().accounts_enabled:
        raise HTTPException(404)


def _sign_in_page(request: Request, *, next_path: str = "/", message: str | None = None,
                  email: str = "", status_code: int = 200) -> Response:
    return page(request, "sign_in.html", {"next": next_path, "message": message, "email": email},
                status_code=status_code, private=True)


@router.get("/sign-in")
def sign_in_form(request: Request, next: str = "/", out: str | None = None) -> Response:
    accounts_on()
    return _sign_in_page(request, next_path=safe_next(next), message=SIGNED_OUT if out else None)


def too_many_tries(address: str) -> bool:
    """Takes from both sign in limits; True when either is empty. Change password uses it too."""
    return not accounts.sign_in_per_minute.take() or not accounts.sign_in_per_address.take(address)


@router.post("/sign-in", dependencies=[Depends(require_same_origin)])
def sign_in(request: Request, email: str = Form(""), password: str = Form(""),
            next: str = Form("/")) -> Response:
    accounts_on()
    target, address = safe_next(next), accounts.normalise_email(email)
    # The limits come first: an empty bucket answers before any password is hashed or checked.
    if too_many_tries(address):
        return _sign_in_page(request, next_path=target, message=TOO_MANY_TRIES, email=email, status_code=429)
    row = graph_accounts.sign_in_row(address) if address else None
    usable = bool(row and row["active"] and row["accepted_at"] is not None and row["password_hash"])
    matches = accounts.check_password(password, row["password_hash"] if usable else _NOBODY)
    if usable and matches:
        response = RedirectResponse(target, status_code=303)
        set_member_cookie(response, row["key"], row["password_hash"])
        return response
    time.sleep(WRONG_PASSPHRASE_DELAY)
    return _sign_in_page(request, next_path=target, message=NOT_MATCHED, email=email)


@router.post("/sign-out", dependencies=[Depends(require_same_origin)])
def sign_out(next: str = Form("")) -> Response:
    accounts_on()
    response = RedirectResponse(safe_next(next) if next else "/sign-in?out=1", status_code=303)
    clear_member_cookie(response)
    return response


STATEMENTS_PAGE = 50
STATEMENTS_MAX = 1000


def _account_page(request: Request, member: Member, *, message: str | None = None, notice: str | None = None,
                  details: dict | None = None, details_message: str | None = None,
                  email_message: str | None = None, status_code: int = 200,
                  shown: int = STATEMENTS_PAGE) -> Response:
    from app import main as site
    details = details or graph_accounts.own_details(member.key) or {"name": member.name}
    # X1: My Statements, 50 at a time; one more is asked for to know whether to offer "Show more".
    shown = min(max(shown, STATEMENTS_PAGE), STATEMENTS_MAX)
    posts = graph_own_posts.my_posts(member.key, shown + 1)
    return page(request, "account.html", {"entered": graph_accounts.who_entered(member.key),
                                          "message": message, "notice": notice, "details": details,
                                          "details_message": details_message, "email_message": email_message,
                                          "posts": site._decorate_posts(posts[:shown], me=member.key),
                                          "more": shown + STATEMENTS_PAGE if len(posts) > shown else None},
                status_code=status_code, private=True)


DONE = {"password": PASSWORD_CHANGED, "details": DETAILS_SAVED}


@router.get("/account")
def account(request: Request, done: str | None = None, shown: int = STATEMENTS_PAGE,
            member: Member = Depends(require_member)) -> Response:
    return _account_page(request, member, notice=DONE.get(done or ""), shown=shown)


@router.post("/account/details", dependencies=[Depends(require_same_origin)])
def change_details(request: Request, name: str = Form(""), country: str = Form(""), postal_code: str = Form(""),
                   member: Member = Depends(require_member)) -> Response:
    """R11, promised 8 Oct: one's own name, country and postal code, at any time. The key comes from
    the cookie only; the postal code is optional (John, 18 Oct)."""
    details = {"name": accounts.person_name(name), "country": accounts.clean_field(country, 80),
               "postal_code": accounts.clean_field(postal_code, 20)}
    if make_key(details["name"]) is None or not details["country"]:
        return _account_page(request, member, details=details, details_message=FILL_IN_NAME_AND_COUNTRY)
    graph_accounts.set_details(member.key, **details)
    return RedirectResponse("/account?done=details", status_code=303)


@router.post("/account/password", dependencies=[Depends(require_same_origin)])
def change_password(request: Request, current: str = Form(""), password: str = Form(""),
                    again: str = Form(""), member: Member = Depends(require_member)) -> Response:
    # The same limits and order as sign in: no scrypt once a bucket is empty.
    if too_many_tries(member.email):
        return _account_page(request, member, message=TOO_MANY_TRIES, status_code=429)
    row = graph_accounts.member(member.key)
    if not row or not accounts.check_password(current, row["password_hash"]):
        time.sleep(WRONG_PASSPHRASE_DELAY)
        return _account_page(request, member, message=NOT_CURRENT)
    problem = accounts.password_problem(password, again)
    if problem:
        return _account_page(request, member, message=problem)
    new_hash = accounts.hash_password(password)
    graph_accounts.set_password(member.key, new_hash)
    response = RedirectResponse("/account?done=password", status_code=303)
    set_member_cookie(response, member.key, new_hash)  # this browser stays in; every other one is out
    return response


@router.get("/forgot-password")
def forgot_form(request: Request) -> Response:
    accounts_on()
    return page(request, "forgot.html", {"message": None, "sent": False}, private=True)


@router.post("/forgot-password", dependencies=[Depends(require_same_origin)])
def forgot_password(request: Request, background: BackgroundTasks, email: str = Form("")) -> Response:
    accounts_on()
    # The form's own site-wide minute (a stranger can only drain this one), then the limit per
    # address, shared with "Send the invitation again" and the back room.
    if not accounts.forgot_per_minute.take():
        return page(request, "forgot.html", {"message": TOO_MANY_TRIES, "sent": False},
                    status_code=429, private=True)
    address = accounts.normalise_email(email)
    # Every address gets the same answer at the same speed: the record write and the two Google
    # calls run after the answer has gone. A busy address is quietly skipped.
    if accounts.looks_like_email(address) and accounts.link_per_address.take(address):
        background.add_task(_send_forgotten_link, getattr(request.state, "request_id", None), address)
    return page(request, "forgot.html", {"message": FORGOT_SENT, "sent": True}, private=True)


def _send_forgotten_link(request_id: str | None, address: str) -> None:
    """Runs after the answer, so a failure here is logged, never shown. The log keeps the request
    id and the kind of failure only: no address, no link."""
    settings = config.get_settings()
    now = datetime.now(timezone.utc)
    secret, token_hash = accounts.new_link()
    try:
        row = graph_accounts.forgot(address, token_hash, accounts.link_expiry("invite", now),
                                    accounts.link_expiry("reset", now))
    except Exception as exc:  # noqa: BLE001  the page has answered
        log.warning(json.dumps({"event": "forgot_failed", "request_id": request_id, "error": type(exc).__name__}))
        return
    if row is None:
        return
    if row["purpose"] == "reset":
        subject, text = emails.password_link(settings.site_name, row["name"],
                                             accounts.link_url(settings.site_url, "reset", secret))
    else:  # entered, not yet accepted; John's root account gets his own wording (X3)
        subject, text = emails.invitation_for(settings.site_name, row["name"], row["inviter_name"], row["relationship"],
                                              accounts.link_url(settings.site_url, "accept", secret))
    mailer.send(row["email"], subject, text, request_id=request_id)


def _open_reset(request: Request, secret: str) -> tuple[dict | None, Response | None]:
    accounts_on()
    here = f"/reset/{secret}"
    # As the accept page: a link longer than any real one is not looked up.
    row = graph_accounts.open_link(accounts.link_hash(secret)) if len(secret) <= 100 else None
    state = accounts.link_state(row, "reset", datetime.now(timezone.utc))
    if state != "ok":
        return None, link_problem(request, "expired_reset" if state == "expired" else "gone", here=here)
    member = current_member(request)
    if member is not None and member.key != row["key"]:
        return None, link_problem(request, "someone_else", here=here)
    return row, None


def _reset_page(request: Request, secret: str, row: dict, message: str | None = None) -> Response:
    return page(request, "reset.html", {"secret": secret, "email": row["email"], "message": message}, private=True)


@router.get("/reset/{secret}")
def reset_form(request: Request, secret: str) -> Response:
    row, problem = _open_reset(request, secret)
    return problem or _reset_page(request, secret, row)


@router.post("/reset/{secret}", dependencies=[Depends(require_same_origin)])
def reset_submit(request: Request, secret: str, password: str = Form(""), again: str = Form("")) -> Response:
    row, problem = _open_reset(request, secret)
    if problem:
        return problem
    message = accounts.password_problem(password, again)
    if message:
        return _reset_page(request, secret, row, message)
    new_hash = accounts.hash_password(password)
    key = graph_accounts.reset_password(accounts.link_hash(secret), new_hash, datetime.now(timezone.utc))
    if key is None:  # used a moment ago, in another tab
        return link_problem(request, "gone", here=f"/reset/{secret}")
    response = RedirectResponse("/?done=reset", status_code=303)
    set_member_cookie(response, key, new_hash)  # this browser is in; every other one is out
    return response
