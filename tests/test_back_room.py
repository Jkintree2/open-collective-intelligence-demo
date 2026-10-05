"""The back room's People section and Sending email line (04_interface.md "Back room additions").
Stubs only: no database, no email."""

import importlib
import logging
import re
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import accounts
from app.auth import KeyedLimit
from app.config import Settings

AUTH = ("any username", "admin password")
NOW = datetime.now(timezone.utc)
ENTERED, JOINED = NOW - timedelta(days=2), NOW - timedelta(days=1)


def row(key, name, *, inviter="Ada Lovelace", relationship="friend", accepted=True, active=True,
        purpose=None, expires=None, admin=False):
    """A Q20 back room row; the email is the key's tail at example.org."""
    return {"key": key, "name": name, "email": f"{key[5:]}@example.org",
            "relationship": relationship if inviter else None, "entered_at": ENTERED if inviter else None,
            "accepted_at": JOINED if accepted else None, "active": active, "purpose": purpose,
            "expires_at": expires, "inviter_name": inviter, "admin": admin}


PEOPLE = [
    row("acct:john", "John Kintree", inviter=None, admin=True),
    row("acct:waiting", "Waiting Person", relationship="work", accepted=False, purpose="invite",
        expires=NOW + timedelta(days=3)),
    row("acct:late", "Late Person", relationship="school", accepted=False, purpose="invite",
        expires=NOW - timedelta(days=1)),
    row("acct:joined", "Joined Person", relationship="neighbor"),
    row("acct:off", "Off Person", active=False),
]


def token(client):
    page = client.get("/admin", auth=AUTH)
    assert page.status_code == 200
    return re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)


@pytest.fixture
def back_room(monkeypatch):
    settings = Settings("gate", "signing secret", "admin password", "unused", "unused", "unused",
                        app_env="local", accounts_enabled=True, site_url="https://record.example")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main.graph, "driver", lambda: pytest.fail("No test may access a database"))
    monkeypatch.setattr(main.graph, "counts", lambda: ({"Person": 5}, {"ENTERED": 4}))
    monkeypatch.setattr(main.graph, "list_posts", lambda limit: [])
    monkeypatch.setattr("app.extract.last_model_error", None)
    monkeypatch.setattr("app.mailer.last_mail_error", None)
    people, calls, sent, state = deepcopy(PEOPLE), [], [], {"send": True}

    def find(key, **want):
        return next((r for r in people if r["key"] == key and all(r[k] == v for k, v in want.items())), None)

    def resend_invitation(key, token_hash, expires_at, inviter_key=None):
        calls.append(("resend", key, token_hash, inviter_key))
        found = find(key, accepted_at=None, active=True)
        return found and {"email": found["email"], "name": found["name"],
                          "inviter_name": found["inviter_name"], "relationship": found["relationship"]}

    def password_link(key, token_hash, expires_at):
        calls.append(("password_link", key, token_hash))
        found = find(key, active=True)
        if found is None or found["accepted_at"] is None:
            return None
        return {"email": found["email"], "name": found["name"]}

    def withdraw(key, inviter_key=None):
        calls.append(("withdraw", key, inviter_key))
        found = find(key, accepted_at=None)
        if found is None or found["inviter_name"] is None:
            return False
        people.remove(found)
        return True

    def set_active(key, active):
        calls.append(("active", key, active))
        found = find(key)
        if found is None or found["admin"]:
            return False
        found["active"] = active
        return True

    monkeypatch.setattr("app.graph_accounts.all_accounts", lambda: deepcopy(people))
    monkeypatch.setattr("app.graph_accounts.resend_invitation", resend_invitation)
    monkeypatch.setattr("app.graph_accounts.password_link", password_link)
    monkeypatch.setattr("app.graph_accounts.withdraw", withdraw)
    monkeypatch.setattr("app.graph_accounts.set_active", set_active)
    monkeypatch.setattr("app.mailer.send", lambda to, subject, text, **kw: sent.append((to, subject, text)) or state["send"])
    monkeypatch.setattr("app.accounts.link_per_address", KeyedLimit(3, 3600))
    client = TestClient(main.app)

    def post(path, **kwargs):
        return client.post(path, auth=AUTH, data={"csrf_token": token(client)}, follow_redirects=False, **kwargs)

    yield SimpleNamespace(client=client, settings=settings, people=people, calls=calls, sent=sent, state=state,
                          post=post, page=lambda path="/admin": client.get(path, auth=AUTH).text)
    client.close()


def test_people_lists_every_account_with_who_entered_it(back_room):
    page = back_room.page()
    entered, joined = ENTERED.strftime("%-d %B %Y"), JOINED.strftime("%-d %B %Y")
    assert '<h2 id="people">People</h2>' in page
    assert f"John Kintree · john@example.org · first account · joined {joined}" in page
    assert f"Joined Person · joined@example.org · entered by Ada Lovelace (neighbor) on {entered} · joined {joined}" in page
    assert f"Waiting Person · waiting@example.org · entered by Ada Lovelace (work) on {entered} · invited, not accepted yet" in page
    assert f"Late Person · late@example.org · entered by Ada Lovelace (school) on {entered} · invitation expired" in page
    assert f"Off Person · off@example.org · entered by Ada Lovelace (friend) on {entered} · switched off" in page
    assert page.index("John Kintree ·") < page.index("Waiting Person ·")   # the record's order, John first


def test_each_row_offers_only_the_buttons_that_apply(back_room):
    from app import routes_admin_people
    assert {r["key"]: r["actions"] for r in routes_admin_people.page_rows()} == {
        "acct:john": ["password_link"],
        "acct:waiting": ["resend", "withdraw"],
        "acct:late": ["resend", "withdraw"],
        "acct:joined": ["password_link", "switch_off"],
        "acct:off": ["switch_on"],
    }
    page = back_room.page()
    assert page.count(">Send the invitation again<") == 2
    assert page.count(">Send a password link<") == 2 and page.count(">Switch on<") == 1
    assert "Switch off Joined Person? They can no longer sign in. Their posts stay." in page
    assert "Switch off John Kintree?" not in page and "Switch off Off Person?" not in page
    assert 'action="/admin/people/acct%3Ajoined/switch-off"' in page
    # Withdraw asks first too: in the back room John withdraws entries other members made.
    for name in ("Waiting Person", "Late Person"):
        assert (f"Withdraw the entry for {name}? Their link stops working and the details entered for them "
                "are removed.") in page
    assert "Withdraw the entry for John Kintree?" not in page and "Withdraw the entry for Joined Person?" not in page
    assert 'action="/admin/people/acct%3Awaiting/withdraw"' in page
    # The two sending buttons submit once; Switch on does not.
    assert re.search(r'action="/admin/people/acct%3Awaiting/resend" data-once>', page)
    assert re.search(r'action="/admin/people/acct%3Ajoined/password-link" data-once>', page)
    assert re.search(r'action="/admin/people/acct%3Aoff/switch-on">', page)


def test_the_page_never_receives_link_fields(back_room):
    from app import routes_admin_people
    for shown in routes_admin_people.page_rows():
        assert set(shown) == {"key", "name", "email", "inviter_name", "relationship", "entered_at",
                              "accepted_at", "state", "first", "actions"}


def test_the_sending_email_line_sits_beside_the_reading_service_line(back_room, monkeypatch):
    page = back_room.page()
    assert "<h2>Sending email</h2><p>No problems recorded.</p>" in page
    assert page.index("<h2>Reading service</h2>") < page.index("<h2>Sending email</h2>") < page.index('id="people"')
    monkeypatch.setattr("app.mailer.last_mail_error", {"time": "2026-10-04T14:02:00+00:00", "http": 400})
    assert "The last email could not be sent, on 4 October 2026, 14:02 UTC." in back_room.page()


def test_without_accounts_the_back_room_is_as_before(back_room, monkeypatch):
    off = replace(back_room.settings, accounts_enabled=False)
    monkeypatch.setattr("app.config.get_settings", lambda: off)
    monkeypatch.setattr("app.auth.get_settings", lambda: off)
    monkeypatch.setattr("app.graph_accounts.all_accounts", lambda: pytest.fail("no accounts are read with accounts off"))
    page = back_room.page()
    assert 'id="people"' not in page and "Sending email" not in page and "<h2>Reading service</h2>" in page


def link_in(text, kind):
    return re.search(rf"https://record\.example/{kind}/(\S+)", text).group(1)


def test_send_the_invitation_again_issues_a_fresh_link_from_the_site_address(back_room):
    result = back_room.post("/admin/people/acct:waiting/resend", headers={"Host": "evil.example"})
    assert result.status_code == 303 and result.headers["location"] == "/admin?done=resent#people"
    _, key, token_hash, inviter_key = back_room.calls[0]
    assert key == "acct:waiting" and inviter_key is None     # the back room version of Q17
    to, subject, text = back_room.sent[0]
    assert to == "waiting@example.org" and subject == "Your invitation to Open Collective Intelligence"
    assert accounts.link_hash(link_in(text, "accept")) == token_hash
    assert "Entered by: Ada Lovelace" in text and "evil.example" not in text
    assert "Invitation sent again." in back_room.page("/admin?done=resent")


def test_johns_own_row_before_his_first_password(back_room):
    back_room.people[0].update(accepted_at=None, purpose="invite", expires_at=NOW + timedelta(days=14))
    page = back_room.page()
    assert "John Kintree · john@example.org · first account · invited, not accepted yet" in page
    from app import routes_admin_people
    john = next(r for r in routes_admin_people.page_rows() if r["key"] == "acct:john")
    assert john["actions"] == ["resend"]                    # never Withdraw
    back_room.post("/admin/people/acct:john/resend")
    to, subject, text = back_room.sent[0]
    assert to == "john@example.org" and subject == "Choose your password for Open Collective Intelligence"
    assert "Entered by" not in text and "https://record.example/accept/" in text


def test_send_a_password_link_to_someone_who_has_joined(back_room):
    result = back_room.post("/admin/people/acct:joined/password-link")
    assert result.headers["location"] == "/admin?done=password_link#people"
    to, subject, text = back_room.sent[0]
    assert to == "joined@example.org" and subject == "Choose a new password for Open Collective Intelligence"
    assert accounts.link_hash(link_in(text, "reset")) == back_room.calls[0][2]
    assert "Password link sent." in back_room.page("/admin?done=password_link")


def test_a_failed_email_says_it_did_not_go(back_room):
    back_room.state["send"] = False
    for path in ("/admin/people/acct:waiting/resend", "/admin/people/acct:joined/password-link"):
        assert back_room.post(path).headers["location"] == "/admin?done=mail_failed#people"
    assert "The email did not go. Please try again in a minute." in back_room.page("/admin?done=mail_failed")


def test_withdraw_switch_off_and_switch_on(back_room):
    assert back_room.post("/admin/people/acct:waiting/withdraw").headers["location"] == "/admin?done=withdrawn#people"
    assert back_room.post("/admin/people/acct:joined/switch-off").headers["location"] == "/admin?done=switched_off#people"
    assert back_room.post("/admin/people/acct:off/switch-on").headers["location"] == "/admin?done=switched_on#people"
    assert back_room.calls == [("withdraw", "acct:waiting", None), ("active", "acct:joined", False),
                               ("active", "acct:off", True)]
    page = back_room.page("/admin?done=switched_off")
    assert "Switched off." in page and "Joined Person · joined@example.org" in page and "Waiting Person" not in page
    assert "Entry withdrawn." in back_room.page("/admin?done=withdrawn")
    assert "Switched on." in back_room.page("/admin?done=switched_on")


def test_john_cannot_switch_himself_off(back_room):
    result = back_room.post("/admin/people/acct:john/switch-off")
    assert result.status_code == 303 and result.headers["location"] == "/admin#people"
    assert back_room.calls == []


@pytest.mark.parametrize("path", [
    "/admin/people/acct:joined/resend",          # accepted: a password link instead
    "/admin/people/acct:waiting/password-link",  # not accepted: the invitation again instead
    "/admin/people/acct:joined/withdraw",        # accepted: switch off instead
    "/admin/people/acct:john/withdraw",          # nobody entered John
    "/admin/people/acct:off/switch-off",         # already off
    "/admin/people/acct:joined/switch-on",       # already on
    "/admin/people/acct:gone/resend",            # withdrawn in another tab
])
def test_a_button_on_a_row_that_changed_meanwhile_changes_nothing(back_room, path):
    result = back_room.post(path)
    assert result.status_code == 303 and result.headers["location"] == "/admin#people"
    assert back_room.calls == [] and back_room.sent == []


def test_a_row_that_changes_between_the_list_and_the_write_sends_nothing(back_room, monkeypatch):
    monkeypatch.setattr("app.graph_accounts.resend_invitation", lambda *args, **kwargs: None)  # accepted just now
    monkeypatch.setattr("app.graph_accounts.password_link", lambda *args, **kwargs: None)      # switched off just now
    assert back_room.post("/admin/people/acct:waiting/resend").headers["location"] == "/admin#people"
    assert back_room.post("/admin/people/acct:joined/password-link").headers["location"] == "/admin#people"
    assert back_room.sent == []


@pytest.mark.parametrize("path", ["/admin/people/acct:waiting/resend", "/admin/people/acct:joined/password-link",
                                  "/admin/people/acct:waiting/withdraw", "/admin/people/acct:joined/switch-off",
                                  "/admin/people/acct:off/switch-on"])
def test_every_people_button_needs_the_back_room_password_and_a_signed_form(back_room, path):
    client = back_room.client
    assert client.post(path).status_code == 401
    assert client.post(path, auth=AUTH, data={"csrf_token": "invalid"}).status_code == 403
    assert client.post(path, auth=AUTH, data={"csrf_token": token(client)},
                       headers={"Origin": "https://other.example"}).status_code == 403
    assert back_room.calls == [] and back_room.sent == []


def test_people_buttons_do_not_exist_without_accounts(back_room, monkeypatch):
    csrf = token(back_room.client)
    off = replace(back_room.settings, accounts_enabled=False)
    monkeypatch.setattr("app.config.get_settings", lambda: off)
    monkeypatch.setattr("app.auth.get_settings", lambda: off)
    result = back_room.client.post("/admin/people/acct:joined/switch-off", auth=AUTH, data={"csrf_token": csrf})
    assert result.status_code == 404 and back_room.calls == []


def test_one_address_gets_only_so_many_links(back_room, monkeypatch):
    monkeypatch.setattr("app.accounts.link_per_address", KeyedLimit(1, 3600))
    assert back_room.post("/admin/people/acct:joined/password-link").headers["location"] == "/admin?done=password_link#people"
    assert back_room.post("/admin/people/acct:joined/password-link").headers["location"] == "/admin?done=address_busy#people"
    assert len(back_room.sent) == 1
    assert ("Too many emails to that address in the last hour. Please try again later."
            in back_room.page("/admin?done=address_busy"))


def test_the_back_room_and_forgot_your_password_share_one_limit(back_room, monkeypatch):
    from app.auth import MinuteBucket
    monkeypatch.setattr("app.accounts.forgot_per_minute", MinuteBucket(capacity=20, period=60))
    monkeypatch.setattr("app.accounts.link_per_address", KeyedLimit(1, 3600))
    back_room.post("/admin/people/acct:joined/password-link")
    asked = []
    monkeypatch.setattr("app.graph_accounts.forgot", lambda *args, **kwargs: asked.append(args) or None)
    back_room.client.post("/forgot-password", data={"email": "joined@example.org"})
    assert asked == []    # this address already had its link from the back room this hour


def test_back_room_sends_log_no_address_name_or_link(back_room, caplog, monkeypatch):
    monkeypatch.setattr(logging.getLogger("oci"), "propagate", True)   # the lifespan turns it off
    caplog.set_level(logging.DEBUG, logger="oci")
    back_room.post("/admin/people/acct:joined/password-link")
    secret = link_in(back_room.sent[0][2], "reset")
    for private in (secret, "joined@example.org", "Joined Person"):
        assert private not in caplog.text
    assert '"event": "back_room_people"' in caplog.text and '"action": "password_link"' in caplog.text
