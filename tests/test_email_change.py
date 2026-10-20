"""X2: changing one's email. The link goes to the new address only, the old one is told, nothing changes
until the link is opened, and the page says the same whether or not the address can be used. No database."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app import accounts, emails
from app.pages import loggable_path
from app.routes_email import ALREADY_YOURS, NOT_AN_EMAIL, TAKEN_MEANWHILE, link_sent

OLD = accounts.hash_password("the old password")
NOW = datetime.now(timezone.utc)


def switch(member_app, monkeypatch, on):
    """EMAIL_CHANGE_ENABLED, X2's own switch (off unless set)."""
    settings = replace(member_app.settings, email_change_enabled=on)
    for target in ("app.config.get_settings", "app.auth.get_settings"):
        monkeypatch.setattr(target, lambda: settings)
    monkeypatch.setattr(member_app.main, "settings", settings)


@pytest.fixture
def change(member_app, monkeypatch):
    switch(member_app, monkeypatch, True)
    member_app.sign_in(password_hash=OLD)
    sent, asked, links = [], [], {}
    taken = {"bob@example.org"}
    monkeypatch.setattr("app.graph_accounts.who_entered", lambda key: None)
    monkeypatch.setattr("app.routes_email.time.sleep", lambda seconds: None)
    monkeypatch.setattr("app.mailer.send", lambda to, subject, text, **kw: sent.append((to, subject, text)) or True)

    def ask(key, email, token_hash, expires_at):
        asked.append((key, email))
        if email in taken:
            return None
        links[token_hash] = {"key": key, "name": "Ada Tester", "email": "ada@example.org", "active": True,
                             "purpose": "email", "expires_at": expires_at, "pending_email": email}
        return {"name": "Ada Tester", "email": "ada@example.org"}

    def confirm(token_hash, now):
        row = links.pop(token_hash, None)
        if row is None:
            return None
        free = row["pending_email"] not in taken
        return {"key": row["key"], "free": free, "old": row["email"], "new": row["pending_email"]}

    monkeypatch.setattr("app.graph_accounts.ask_email_change", ask)
    monkeypatch.setattr("app.graph_accounts.confirm_email_change", confirm)
    monkeypatch.setattr("app.graph_accounts.open_link", lambda token_hash: links.get(token_hash))
    member_app.sent, member_app.asked, member_app.links, member_app.taken = sent, asked, links, taken
    return member_app


def form(**fields):
    return {"email": "ada.new@example.org", "current": "the old password", **fields}


def secret_in(text):
    return text.split("/email/")[1].split()[0]


def test_your_account_offers_the_change(change):
    page = change.client.get("/account").text
    assert "<h2>Change your email</h2>" in page and 'action="/account/email"' in page
    assert "Send a link to the new email" in page
    assert page.index("Change your password") < page.index("Change your email") < page.index("My Statements")


@pytest.mark.parametrize("fields, message", [
    ({"current": "wrong"}, "That is not your current password."),
    ({"email": "not an address"}, NOT_AN_EMAIL),
    ({"email": " ADA@example.org "}, ALREADY_YOURS)])
def test_a_refused_change_says_why_and_sends_nothing(change, fields, message):
    page = change.client.post("/account/email", data=form(**fields)).text
    assert message in page and change.sent == [] and change.asked == []


def test_the_link_goes_to_the_new_address_and_the_old_one_is_told(change):
    page = change.client.post("/account/email", data=form(email=" Ada.New@Example.org")).text
    assert link_sent("ada.new@example.org", "ada@example.org") in page
    assert "check your spam folder" in page
    (to_new, subject_new, text_new), (to_old, subject_old, text_old) = change.sent
    assert to_new == "ada.new@example.org" and subject_new.startswith("Confirm your new email for ")
    assert "https://record.example/email/" in text_new
    assert to_old == "ada@example.org" and "ada.new@example.org" in text_old
    assert "/email/" not in text_old  # the link never goes to the old address
    assert change.accounts["acct:ada"]["email"] == "ada@example.org"  # nothing changes yet


def test_an_address_another_account_holds_gets_the_same_answer_and_no_email(change):
    page = change.client.post("/account/email", data=form(email="bob@example.org")).text
    assert link_sent("bob@example.org", "ada@example.org") in page
    assert change.asked == [("acct:ada", "bob@example.org")] and change.sent == []


def test_opening_the_link_asks_first_then_changes_the_email(change):
    change.client.post("/account/email", data=form())
    secret = secret_in(change.sent[0][2])
    page = change.client.get(f"/email/{secret}").text
    assert "From now on, sign in with ada.new@example.org." in page
    assert "Your old address, ada@example.org, stays on your account's record as an earlier one." in page
    assert change.links  # opening the page changes nothing: a mail scanner may open links
    done = change.client.post(f"/email/{secret}").text
    assert "Your email is changed. From now on, sign in with ada.new@example.org." in done
    assert 'href="/account"' in done
    assert "This link no longer works." in change.client.post(f"/email/{secret}").text


def test_an_address_taken_meanwhile_leaves_the_email_as_it_was(change):
    change.client.post("/account/email", data=form())
    secret = secret_in(change.sent[0][2])
    change.taken.add("ada.new@example.org")
    assert TAKEN_MEANWHILE in change.client.post(f"/email/{secret}").text


def test_an_expired_link_says_so(change):
    change.client.post("/account/email", data=form())
    secret = secret_in(change.sent[0][2])
    next(iter(change.links.values()))["expires_at"] = NOW - timedelta(minutes=1)
    assert "This link has expired. You can ask for a new one on Your account." in change.client.get(f"/email/{secret}").text


def test_the_link_never_reaches_the_log():
    assert loggable_path("/email/abc123") == "/email/…"
    assert accounts.link_url("https://record.example", "email", "abc") == "https://record.example/email/abc"
    assert accounts.link_expiry("email", NOW) == NOW + timedelta(hours=24)



def test_the_switch_is_off_unless_set():
    from app.config import load_settings
    base = {"DEMO_PASSPHRASE": "p", "SECRET_KEY": "s", "ADMIN_TOKEN": "a", "NEO4J_URI": "neo4j://x",
            "NEO4J_USERNAME": "n", "NEO4J_PASSWORD": "w"}
    assert load_settings(base).email_change_enabled is False
    assert load_settings({**base, "EMAIL_CHANGE_ENABLED": "true"}).email_change_enabled is True


def test_with_the_switch_off_there_is_no_form_and_no_pages(change, monkeypatch):
    """EMAIL_CHANGE_ENABLED unset: Your account goes from the password form to My Statements, and the
    change of email pages answer not found, even for a link sent while it was on."""
    assert change.client.post("/account/email", data=form()).status_code == 200
    secret = secret_in(change.sent[0][2])
    switch(change, monkeypatch, False)
    page = change.client.get("/account").text
    assert "Change your email" not in page and "/account/email" not in page
    assert page.index("Change password") < page.index("My Statements")
    assert change.client.post("/account/email", data=form(email="ada.other@example.org")).status_code == 404
    assert change.client.get(f"/email/{secret}").status_code == 404
    assert change.client.post(f"/email/{secret}").status_code == 404
    assert len(change.asked) == 1  # the second ask never reached the record
