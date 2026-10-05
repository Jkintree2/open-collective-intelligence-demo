import re
from datetime import datetime, timezone

import pytest

from app import accounts

OLD = accounts.hash_password("the old password")


@pytest.fixture
def signed_in(member_app, monkeypatch):
    member_app.sign_in(password_hash=OLD)
    saved = []
    monkeypatch.setattr("app.graph_accounts.set_password",
                        lambda key, password_hash: saved.append((key, password_hash))
                        or member_app.accounts[key].update(password_hash=password_hash))
    monkeypatch.setattr("app.graph_accounts.who_entered", lambda key: {
        "inviter_name": "John Kintree", "relationship": "friend",
        "entered_at": datetime(2026, 10, 4, 9, 30, tzinfo=timezone.utc)})
    monkeypatch.setattr("app.routes_accounts.time.sleep", lambda seconds: None)
    member_app.saved = saved
    return member_app


def test_account_page_offers_a_new_password(signed_in):
    page = signed_in.client.get("/account")
    assert page.status_code == 200
    assert "Ada Lovelace · ada@example.org" in page.text
    assert "Entered by John Kintree (Friend) on 4 October 2026." in page.text
    assert page.text.count('autocomplete="new-password"') == 2
    assert 'autocomplete="current-password"' in page.text
    # The email is a visible read-only username field, so a phone saves the new password under it.
    username = re.search(r'<input[^>]*autocomplete="username"[^>]*>', page.text).group(0)
    assert 'value="ada@example.org"' in username and "readonly" in username
    assert "hidden" not in username
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["referrer-policy"] == "same-origin"


@pytest.mark.parametrize("current, new, again, message", [
    ("not the password", "a brand new password", "a brand new password", "That is not your current password."),
    ("the old password", "short", "short", "Please use at least 10 characters for your password."),
    ("the old password", "a brand new password", "a brand new passwork", "The two passwords are not the same."),
])
def test_a_refused_change_says_why_and_changes_nothing(signed_in, current, new, again, message):
    result = signed_in.client.post("/account/password", data={"current": current, "password": new, "again": again})
    assert message in result.text and signed_in.saved == []


def test_changing_the_password_signs_out_other_devices(signed_in):
    other_device = signed_in.client.cookies.get(accounts.MEMBER_COOKIE)
    result = signed_in.client.post("/account/password", data={"current": "the old password",
        "password": "a brand new password", "again": "a brand new password"}, follow_redirects=False)
    assert result.status_code == 303 and result.headers["location"] == "/account?done=password"
    key, new_hash = signed_in.saved[0]
    assert key == "acct:ada" and accounts.check_password("a brand new password", new_hash)
    # This browser got a fresh cookie and stays in; the old cookie, on another phone, is out.
    assert signed_in.client.get("/", follow_redirects=False).status_code == 200
    assert "Your password is changed. You are signed out everywhere else." in signed_in.client.get("/account?done=password").text
    signed_in.set_cookie(other_device)  # replaces this browser's cookie, as the other phone holds it
    assert signed_in.client.get("/", follow_redirects=False).status_code == 303


def test_a_flood_of_wrong_current_passwords_never_reaches_scrypt(signed_in, monkeypatch):
    from app.auth import MinuteBucket
    monkeypatch.setattr("app.accounts.sign_in_per_minute", MinuteBucket(capacity=0, period=60))
    monkeypatch.setattr("app.accounts.check_password", lambda *args: pytest.fail("scrypt ran with no token"))
    result = signed_in.client.post("/account/password", data={"current": "the old password",
        "password": "a brand new password", "again": "a brand new password"})
    assert result.status_code == 429 and "Too many tries. Please wait a minute and try again." in result.text
    assert signed_in.saved == []


def test_the_header_offers_the_account_page(signed_in):
    assert '<a href="/account">Your account</a>' in signed_in.client.get("/").text


def test_the_password_form_refuses_a_post_from_another_site(signed_in):
    result = signed_in.client.post("/account/password", data={"current": "the old password",
        "password": "a brand new password", "again": "a brand new password"},
        headers={"Origin": "https://elsewhere.example"})
    assert "Please reload the page and try again." in result.text and signed_in.saved == []


def test_the_account_page_needs_an_account(member_app):
    assert member_app.client.get("/account", follow_redirects=False).status_code == 303
