"""Sign in, sign out, your account and changing the password (sub-plan A). The reset pages join in Task A8."""

import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import accounts, config, graph_accounts
from app.auth import TOO_MANY_TRIES, WRONG_PASSPHRASE_DELAY
from app.members import Member, clear_member_cookie, require_member, require_same_origin, safe_next, set_member_cookie
from app.pages import page

router = APIRouter()

# Client facing copy, word for word from docs/planning/04_interface.md.
NOT_MATCHED = "That email and password did not match. Check them and try again."
SIGNED_OUT = "You are signed out."
NOT_CURRENT = "That is not your current password."
PASSWORD_CHANGED = "Your password is changed. You are signed out everywhere else."

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


def _account_page(request: Request, member: Member, *, message: str | None = None,
                  notice: str | None = None, status_code: int = 200) -> Response:
    return page(request, "account.html", {"entered": graph_accounts.who_entered(member.key),
                                          "message": message, "notice": notice},
                status_code=status_code, private=True)


@router.get("/account")
def account(request: Request, done: str | None = None, member: Member = Depends(require_member)) -> Response:
    return _account_page(request, member, notice=PASSWORD_CHANGED if done == "password" else None)


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
