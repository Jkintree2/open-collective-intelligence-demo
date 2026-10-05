import re

import pytest

from app import accounts

GOOD = accounts.hash_password("a good long password")


@pytest.fixture
def door(member_app, monkeypatch):
    rows = {"ada@example.org": {"key": "acct:ada", "password_hash": GOOD, "active": True, "accepted_at": "set"},
            "bob@example.org": {"key": "acct:bob", "password_hash": None, "active": True, "accepted_at": None},
            "cy@example.org": {"key": "acct:cy", "password_hash": GOOD, "active": False, "accepted_at": "set"}}
    monkeypatch.setattr("app.graph_accounts.sign_in_row", lambda email: rows.get(email))
    monkeypatch.setattr("app.routes_accounts.time.sleep", lambda seconds: None)
    member_app.accounts["acct:ada"] = {"key": "acct:ada", "name": "Ada Tester", "email": "ada@example.org",
                                       "admin": False, "password_hash": GOOD}
    return member_app


def test_sign_in_page_lets_a_phone_fill_and_save_the_password(door):
    page = door.client.get("/sign-in")
    assert page.status_code == 200
    assert re.search(r'<input id="email" name="email" type="email" autocomplete="username" autocapitalize="none" spellcheck="false"', page.text)
    assert 'autocomplete="current-password"' in page.text
    assert "A closed test of a shared record of what people are claiming, proposing and citing." in page.text
    assert page.headers["cache-control"] == "no-store" and page.headers["referrer-policy"] == "same-origin"


def test_signing_in_opens_the_page_asked_for(door):
    result = door.client.post("/sign-in", data={"email": " Ada@Example.org ", "password": "a good long password",
                                                "next": "/issues?sort=recent"}, follow_redirects=False)
    assert result.status_code == 303 and result.headers["location"] == "/issues?sort=recent"
    assert door.client.get("/issues", follow_redirects=False).status_code == 200


def test_an_unsafe_next_goes_home(door):
    result = door.client.post("/sign-in", data={"email": "ada@example.org", "password": "a good long password",
                                                "next": "//evil.example/"}, follow_redirects=False)
    assert result.headers["location"] == "/"


@pytest.mark.parametrize("email, password", [
    ("ada@example.org", "the wrong password"),   # wrong password
    ("nobody@example.org", "a good long password"),  # unknown address
    ("bob@example.org", "a good long password"),  # entered, not yet accepted
    ("cy@example.org", "a good long password"),   # switched off
    ("", ""),
])
def test_every_failure_gets_the_same_answer(door, email, password):
    result = door.client.post("/sign-in", data={"email": email, "password": password})
    assert result.status_code == 200
    assert "That email and password did not match. Check them and try again." in result.text
    assert accounts.MEMBER_COOKIE not in result.headers.get("set-cookie", "")


def test_too_many_tries_from_one_address_wait_a_minute(door, monkeypatch):
    from app.auth import KeyedLimit
    monkeypatch.setattr("app.accounts.sign_in_per_address", KeyedLimit(1, 60))
    door.client.post("/sign-in", data={"email": "ada@example.org", "password": "wrong one here"})
    result = door.client.post("/sign-in", data={"email": " ADA@example.org", "password": "wrong one here"})
    assert result.status_code == 429
    assert "Too many tries. Please wait a minute and try again." in result.text
    other = door.client.post("/sign-in", data={"email": "bob@example.org", "password": "wrong one here"})
    assert other.status_code == 200  # another address has its own count


def test_an_empty_bucket_refuses_even_the_right_password(door, monkeypatch):
    """Item 1 of the 5 October review: the limits come before scrypt, so a flood costs no memory."""
    from app.auth import MinuteBucket
    monkeypatch.setattr("app.accounts.sign_in_per_minute", MinuteBucket(capacity=1, period=3600))
    door.client.post("/sign-in", data={"email": "nobody@example.org", "password": "anything at all"})
    checked = []
    monkeypatch.setattr("app.accounts.check_password", lambda *args: checked.append(args) or True)
    result = door.client.post("/sign-in", data={"email": "ada@example.org", "password": "a good long password"},
                              follow_redirects=False)
    assert result.status_code == 429 and "Too many tries" in result.text
    assert checked == [] and accounts.MEMBER_COOKIE not in result.headers.get("set-cookie", "")


def test_failed_sign_ins_leave_the_reading_service_alone(door):
    """The passphrase's and reading service's bucket is not the sign in bucket."""
    for _ in range(8):
        door.client.post("/sign-in", data={"email": "ada@example.org", "password": "the wrong password"})
    assert door.main.attempt_bucket.has_token()


def test_signing_out_clears_the_cookie(door):
    door.client.post("/sign-in", data={"email": "ada@example.org", "password": "a good long password"})
    result = door.client.post("/sign-out", follow_redirects=False)
    assert result.headers["location"] == "/sign-in?out=1"
    assert "You are signed out." in door.client.get("/sign-in?out=1").text
    assert door.client.get("/", follow_redirects=False).status_code == 303


def test_sign_in_does_not_exist_without_accounts(member_app, monkeypatch):
    from dataclasses import replace
    off = replace(member_app.settings, accounts_enabled=False)
    monkeypatch.setattr("app.config.get_settings", lambda: off)
    assert member_app.client.get("/sign-in").status_code == 404


def test_request_log_cuts_links_out_of_the_path(door, caplog, monkeypatch):
    import logging
    # From B5 and A8 on these pages open the link; no link is known here, so each answers its
    # "no longer works" page (here, a 404 until those pages exist), never a 500.
    monkeypatch.setattr("app.graph_accounts.open_link", lambda token_hash: None, raising=False)
    monkeypatch.setattr(logging.getLogger("oci"), "propagate", True)  # the lifespan turns it off
    caplog.set_level(logging.INFO, logger="oci")
    for path in ("/accept/SECRETLINK123", "/reset/SECRETLINK456"):
        assert door.client.get(path).status_code in (200, 404)
    assert "SECRETLINK" not in caplog.text
    assert '"path": "/accept/\\u2026"' in caplog.text and '"path": "/reset/\\u2026"' in caplog.text
