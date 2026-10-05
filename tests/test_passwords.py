import re
from datetime import datetime, timedelta, timezone

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
    assert "Entered by John Kintree (friend) on 4 October 2026." in page.text
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


SAME = "If that address belongs to someone taking part, an email with a link is on its way."


@pytest.fixture
def forgot(member_app, monkeypatch):
    from dataclasses import replace
    settings = replace(member_app.settings, site_url="https://record.example")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    rows = {"ada@example.org": {"email": "ada@example.org", "name": "Ada Lovelace", "purpose": "reset",
                                "inviter_name": "John Kintree", "relationship": "friend"},
            "bob@example.org": {"email": "bob@example.org", "name": "Bob", "purpose": "invite",
                                "inviter_name": "Ada Lovelace", "relationship": "work"},
            # John's root account from make_admin.py, not yet accepted: nobody entered him (X3).
            "john@example.org": {"email": "john@example.org", "name": "John Kintree", "purpose": "invite",
                                 "inviter_name": None, "relationship": None}}
    links = []
    monkeypatch.setattr("app.graph_accounts.forgot", lambda email, token_hash, invite_expires_at, reset_expires_at:
                        links.append(token_hash) or rows.get(email))
    sent = []
    monkeypatch.setattr("app.routes_accounts.mailer.send", lambda to, subject, text, **kw: sent.append((to, subject, text)) or True)
    from app.auth import KeyedLimit
    monkeypatch.setattr("app.accounts.link_per_address", KeyedLimit(3, 3600))
    member_app.sent, member_app.links = sent, links
    return member_app


@pytest.mark.parametrize("email", ["ada@example.org", "bob@example.org", "nobody@example.org", "not an email"])
def test_forgot_password_says_the_same_for_every_address(forgot, email):
    result = forgot.client.post("/forgot-password", data={"email": email})
    assert result.status_code == 200 and SAME in result.text


def test_forgot_password_sends_a_password_link_to_an_account(forgot):
    forgot.client.post("/forgot-password", data={"email": " ADA@example.org"}, headers={"Host": "evil.example"})
    to, subject, text = forgot.sent[0]
    assert to == "ada@example.org" and subject == "Choose a new password for Open Collective Intelligence"
    assert "https://record.example/reset/" in text and "evil.example" not in text
    assert "The link works once, for one hour." in text


def test_forgot_password_sends_an_unaccepted_person_their_invitation_again(forgot):
    forgot.client.post("/forgot-password", data={"email": "bob@example.org"})
    to, subject, text = forgot.sent[0]
    assert subject == "Your invitation to Open Collective Intelligence"
    assert "Entered by: Ada Lovelace" in text and "https://record.example/accept/" in text


def test_johns_first_link_comes_in_his_own_wording(forgot):
    """X3: make_admin.py sends nothing; John asks here, and nobody entered him."""
    forgot.client.post("/forgot-password", data={"email": "john@example.org"})
    to, subject, text = forgot.sent[0]
    assert to == "john@example.org" and subject == "Choose your password for Open Collective Intelligence"
    assert "https://record.example/accept/" in text and "Entered by" not in text and "None" not in text


def test_nobody_gets_an_email_for_an_unknown_address(forgot):
    forgot.client.post("/forgot-password", data={"email": "nobody@example.org"})
    assert forgot.sent == []


def test_one_address_gets_at_most_three_links_an_hour(forgot):
    for _ in range(5):
        assert SAME in forgot.client.post("/forgot-password", data={"email": "ada@example.org"}).text
    assert len(forgot.sent) == 3


def test_a_known_address_does_its_work_after_the_answer(forgot, monkeypatch):
    """Item 12 of the 5 October review: the record write and the two Google calls happen in a
    background task, so the answer for a real address comes as fast as for a stranger's."""
    order = []
    monkeypatch.setattr("app.routes_accounts._send_forgotten_link",
                        lambda request_id, address: order.append(("sent", address)))
    from starlette.background import BackgroundTasks
    real_call = BackgroundTasks.__call__

    async def after_the_answer(self, *args):
        order.append(("answered", None))
        await real_call(self, *args)
    monkeypatch.setattr(BackgroundTasks, "__call__", after_the_answer)
    forgot.client.post("/forgot-password", data={"email": "ada@example.org"})
    assert order == [("answered", None), ("sent", "ada@example.org")]


def test_the_forgot_form_has_its_own_minute(forgot, monkeypatch):
    from app.auth import MinuteBucket
    monkeypatch.setattr("app.accounts.forgot_per_minute", MinuteBucket(capacity=1, period=3600))
    forgot.client.post("/forgot-password", data={"email": "ada@example.org"})
    refused = forgot.client.post("/forgot-password", data={"email": "bob@example.org"})
    assert refused.status_code == 429 and "Too many tries. Please wait a minute and try again." in refused.text


def test_the_page_offers_a_link_from_sign_in(forgot):
    assert '<a href="/forgot-password">Forgot your password?</a>' in forgot.client.get("/sign-in").text
    page = forgot.client.get("/forgot-password").text
    assert "Enter the email address you were invited with, and we will send you a link to choose a password." in page
    assert 'autocomplete="username"' in page


def test_the_forgot_pages_are_private_and_missing_with_accounts_off(forgot, monkeypatch):
    page = forgot.client.get("/forgot-password")
    assert page.headers["referrer-policy"] == "same-origin" and page.headers["cache-control"] == "no-store"
    from dataclasses import replace
    off = replace(forgot.settings, accounts_enabled=False)
    monkeypatch.setattr("app.config.get_settings", lambda: off)
    assert forgot.client.get("/forgot-password").status_code == 404
    assert forgot.client.post("/forgot-password", data={"email": "ada@example.org"}).status_code == 404
    assert forgot.client.get("/reset/anything").status_code == 404


NOW = datetime.now(timezone.utc)


@pytest.fixture
def reset(member_app, monkeypatch):
    row = {"key": "acct:ada", "name": "Ada Lovelace", "email": "ada@example.org", "purpose": "reset",
           "active": True, "accepted_at": NOW, "inviter_name": None, "relationship": None}
    links = {accounts.link_hash("goodlink"): {**row, "expires_at": NOW + timedelta(hours=1)},
             accounts.link_hash("oldlink"): {**row, "expires_at": NOW - timedelta(minutes=1)}}
    monkeypatch.setattr("app.graph_accounts.open_link", lambda token_hash: links.get(token_hash))

    def reset_password(token_hash, password_hash, now):
        found = links.pop(token_hash, None)
        if found is None:
            return None
        member_app.accounts["acct:ada"] = {"key": "acct:ada", "name": "Ada Lovelace", "email": "ada@example.org",
                                           "admin": False, "password_hash": password_hash}
        return found["key"]
    monkeypatch.setattr("app.graph_accounts.reset_password", reset_password)
    return member_app


def test_reset_page_offers_a_new_password_under_the_email(reset):
    page = reset.client.get("/reset/goodlink")
    assert page.status_code == 200
    assert 'value="ada@example.org"' in page.text and 'autocomplete="username"' in page.text
    assert page.text.count('autocomplete="new-password"') == 2
    assert page.headers["referrer-policy"] == "same-origin" and page.headers["cache-control"] == "no-store"


def test_a_reset_link_works_once(reset):
    result = reset.client.post("/reset/goodlink", data={"password": "a brand new password", "again": "a brand new password"},
                               follow_redirects=False)
    assert result.status_code == 303 and result.headers["location"] == "/?done=reset"
    assert "Your new password is saved. You are signed out everywhere else." in reset.client.get("/?done=reset").text
    again = reset.client.get("/reset/goodlink")
    assert "This link no longer works." in again.text


def test_the_new_password_signs_this_browser_in_and_the_old_cookie_out(reset):
    old = accounts.make_member_cookie("acct:ada", OLD, reset.settings.secret_key)
    reset.client.post("/reset/goodlink", data={"password": "a brand new password", "again": "a brand new password"})
    saved = reset.accounts["acct:ada"]["password_hash"]
    assert accounts.check_password("a brand new password", saved)
    cookie = reset.client.cookies.get(accounts.MEMBER_COOKIE)
    assert accounts.member_cookie_valid(cookie, saved, reset.settings.secret_key)
    assert not accounts.member_cookie_valid(old, saved, reset.settings.secret_key)


def test_a_short_or_unmatched_new_password_is_refused_and_the_link_kept(reset):
    short = reset.client.post("/reset/goodlink", data={"password": "short", "again": "short"})
    assert "Please use at least 10 characters for your password." in short.text
    differ = reset.client.post("/reset/goodlink", data={"password": "a brand new password", "again": "another new password"})
    assert "The two passwords are not the same." in differ.text
    assert reset.client.get("/reset/goodlink").status_code == 200


def test_a_mangled_reset_link_is_not_looked_up(reset, monkeypatch):
    """Second review, item 6: the same length guard as B5's accept page."""
    monkeypatch.setattr("app.graph_accounts.open_link", lambda token_hash: pytest.fail("not looked up"))
    page = reset.client.get("/reset/" + "a" * 400)
    assert page.status_code == 200 and "This link no longer works." in page.text


def test_an_expired_reset_link_says_so(reset):
    page = reset.client.get("/reset/oldlink").text
    assert "This link has expired. You can ask for a new one." in page


def test_a_reset_link_opened_while_someone_else_is_signed_in(reset):
    reset.sign_in(key="acct:bob", name="Bob", email="bob@example.org")
    page = reset.client.get("/reset/goodlink").text
    assert "You are signed in as Bob. This link is for someone else." in page
    assert 'name="next" value="/reset/goodlink"' in page


def test_an_invitation_link_does_not_open_the_reset_page(reset, monkeypatch):
    invite = {"key": "acct:bob", "name": "Bob", "email": "bob@example.org", "purpose": "invite", "active": True,
              "accepted_at": None, "expires_at": NOW + timedelta(days=1), "inviter_name": "Ada", "relationship": "work"}
    monkeypatch.setattr("app.graph_accounts.open_link", lambda token_hash: invite)
    assert "This link no longer works." in reset.client.get("/reset/goodlink").text


def test_the_forgot_form_is_sent_once_per_tap(forgot):
    page = forgot.client.get("/forgot-password").text
    assert re.search(r'<form method="post" action="/forgot-password"[^>]*data-once', page)
    from app import main
    assert f'/static/once.js?v={main.templates.env.globals["asset_version"]}' in page
