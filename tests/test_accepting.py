import re
from datetime import datetime, timedelta, timezone

import pytest

from app import accounts

NOW = datetime.now(timezone.utc)


def link_row(**extra):
    return {"key": "acct:bob", "name": "Bob Smith", "email": "bob@example.org", "country": "Germany",
            "postal_code": "10115", "active": True, "accepted_at": None, "purpose": "invite",
            "expires_at": NOW + timedelta(days=3), "inviter_name": "Ada Lovelace", "relationship": "neighbor", **extra}


@pytest.fixture
def invited(member_app, monkeypatch):
    links = {accounts.link_hash("goodlink"): link_row(),
             accounts.link_hash("oldlink"): link_row(expires_at=NOW - timedelta(days=1)),
             accounts.link_hash("rootlink"): link_row(key="acct:john", name="John Kintree", inviter_name=None, relationship=None)}
    accepted = []
    monkeypatch.setattr("app.graph_accounts.open_link", lambda token_hash: links.get(token_hash))

    def accept(token_hash, *, name, country, postal_code, password_hash, now):
        row = links.pop(token_hash, None)
        if row is None:
            return None
        accepted.append({"name": name, "country": country, "postal_code": postal_code, "password_hash": password_hash})
        member_app.accounts[row["key"]] = {"key": row["key"], "name": name, "email": row["email"],
                                           "admin": False, "password_hash": password_hash}
        return row["key"]
    monkeypatch.setattr("app.graph_accounts.accept", accept)
    member_app.accepted = accepted
    return member_app


def test_the_acceptance_page_lets_a_phone_suggest_and_save_a_password(invited):
    page = invited.client.get("/accept/goodlink")
    assert page.status_code == 200
    text = page.text
    assert "Welcome to Open Collective Intelligence" in text
    assert "Ada Lovelace entered you. Please check your details and choose a password." in text
    assert "How you know Ada Lovelace: Neighbor" in text
    assert re.search(r'name="username" type="email" value="bob@example.org" autocomplete="username" readonly', text)
    assert text.count('autocomplete="new-password"') == 2
    assert 'autocomplete="country-name"' in text and 'autocomplete="postal-code"' in text
    assert "At least 10 characters. Your browser may offer a strong password and remember it for you." in text
    assert "reads what you write to fill in the form" in text  # the shared paragraphs
    assert page.headers["referrer-policy"] == "same-origin" and page.headers["cache-control"] == "no-store"


def test_johns_own_link_says_choose_your_password(invited):
    text = invited.client.get("/accept/rootlink").text
    assert "<h1>Choose your password</h1>" in text and "entered you" not in text and "How you know" not in text


@pytest.mark.parametrize("change, message", [
    ({"name": "  "}, "Please fill in your name."),
    ({"password": "short", "again": "short"}, "Please use at least 10 characters for your password."),
    ({"again": "something else entirely"}, "The two passwords are not the same."),
])
def test_a_refused_acceptance_says_why(invited, change, message):
    data = {"name": "Bob Smith", "country": "Germany", "postal_code": "10115",
            "password": "a good long password", "again": "a good long password", **change}
    assert message in invited.client.post("/accept/goodlink", data=data).text
    assert invited.accepted == []


def test_accepting_takes_corrected_details_signs_in_and_welcomes(invited):
    result = invited.client.post("/accept/goodlink", follow_redirects=False, data={
        "name": "  robert   smith. ", "country": "Deutschland", "postal_code": "10117", "relationship": "family",
        "password": "a good long password", "again": "a good long password"})
    assert result.status_code == 303 and result.headers["location"] == "/?done=welcome"
    saved = invited.accepted[0]
    # The name is cleaned as the record expects (03_schema.md, Person.name); the relationship stays.
    assert (saved["name"], saved["country"], saved["postal_code"]) == ("Robert smith", "Deutschland", "10117")
    assert accounts.check_password("a good long password", saved["password_hash"])
    assert "Welcome, Robert smith. You are signed in." in invited.client.get("/?done=welcome").text
    assert "Welcome" not in invited.client.get("/?done=nonsense").text


def test_a_link_works_once(invited):
    data = {"name": "Bob", "country": "G", "postal_code": "1", "password": "a good long password", "again": "a good long password"}
    invited.client.post("/accept/goodlink", data=data)
    invited.client.cookies.clear()
    again = invited.client.get("/accept/goodlink")
    assert again.status_code == 200
    assert "This link no longer works. It may have been used already, or a newer one sent." in again.text
    assert invited.client.post("/accept/goodlink", data=data).status_code == 200


def test_an_expired_invitation_says_who_to_ask(invited):
    text = invited.client.get("/accept/oldlink").text
    assert "This invitation has expired. Please ask Ada Lovelace to send a new one." in text


@pytest.mark.parametrize("secret", ["x", "a" * 400, "%00%ff", "..%2F..%2Fadmin"])
def test_a_mangled_link_gets_the_no_longer_works_page(invited, secret):
    result = invited.client.get(f"/accept/{secret}")
    # A path that is not /accept/<one part> at all (the last one, once decoded) is no page: 404.
    assert result.status_code in (200, 404)
    if result.status_code == 200:
        assert "This link no longer works. It may have been used already, or a newer one sent." in result.text
        assert 'name="password"' not in result.text


def test_a_link_opened_while_someone_else_is_signed_in(invited):
    invited.sign_in(key="acct:ada", name="Ada Lovelace", email="ada@example.org")
    text = invited.client.get("/accept/goodlink").text
    assert "You are signed in as Ada Lovelace. This link is for someone else." in text
    assert '<form method="post" action="/sign-out">' in text and 'name="next" value="/accept/goodlink"' in text
    assert 'name="password"' not in text
    # Signing out and continuing shows the acceptance page.
    invited.client.post("/sign-out", data={"next": "/accept/goodlink"})
    assert "Ada Lovelace entered you." in invited.client.get("/accept/goodlink").text


def test_accepting_does_not_exist_without_accounts(member_app, monkeypatch):
    from dataclasses import replace
    monkeypatch.setattr("app.config.get_settings", lambda: replace(member_app.settings, accounts_enabled=False))
    assert member_app.client.get("/accept/goodlink").status_code == 404


def test_each_acceptance_label_sits_in_its_own_row_above_its_field(invited):
    text = invited.client.get("/accept/goodlink").text
    rows = re.findall(r'<div class="field">\s*<label for="(\w+)">[^<]*</label>\s*<input id="(\w+)"[^>]*>\s*</div>', text)
    assert [a for a, _ in rows] == ["name", "username", "country", "postal_code", "password", "again"]
    assert all(a == b for a, b in rows)
    assert text.count("<input id=") == len(rows)
