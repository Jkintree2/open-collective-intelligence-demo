import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest

from app import accounts
from app.graph_accounts import EmailTaken

NOW = datetime.now(timezone.utc)
FORM = {"name": "Bob Smith", "email": " Bob@Example.org ", "country": "Germany", "postal_code": "10115",
        "relationship": "neighbor", "agreed": "yes"}
LISTED = [
    {"key": "acct:joined", "name": "Joined Person", "email": "j@example.org", "relationship": "friend",
     "entered_at": NOW, "accepted_at": NOW, "active": True, "purpose": None, "expires_at": None},
    {"key": "acct:waiting", "name": "Waiting Person", "email": "w@example.org", "relationship": "work",
     "entered_at": NOW, "accepted_at": None, "active": True, "purpose": "invite", "expires_at": NOW + timedelta(days=3)},
    {"key": "acct:late", "name": "Late Person", "email": "l@example.org", "relationship": "school",
     "entered_at": NOW, "accepted_at": None, "active": True, "purpose": "invite", "expires_at": NOW - timedelta(days=1)},
    {"key": "acct:off", "name": "Gone Person", "email": "g@example.org", "relationship": "health",
     "entered_at": NOW, "accepted_at": NOW, "active": False, "purpose": None, "expires_at": None},
]


@pytest.fixture
def people(member_app, monkeypatch):
    member_app.sign_in()
    entries, sent, resent, withdrawn = [], [], [], []
    state = {"taken": set(), "recent": None, "send": True}

    def enter_person(**kw):
        if kw["email"] in state["taken"]:
            raise EmailTaken()
        state["taken"].add(kw["email"])
        entries.append(kw)
        return True

    def entered_by(key):
        made = [{"key": e["key"], "name": e["name"], "email": e["email"], "relationship": e["relationship"],
                 "entered_at": NOW, "accepted_at": None, "active": True, "purpose": "invite",
                 "expires_at": NOW + timedelta(days=14)} for e in entries]
        return made + LISTED

    def resend_invitation(key, token_hash, expires_at, inviter_key=None):
        resent.append((key, token_hash, inviter_key))
        row = next(r for r in entered_by(inviter_key) if r["key"] == key)
        return {"email": row["email"], "name": row["name"], "inviter_name": "Ada Lovelace",
                "relationship": row["relationship"]}

    monkeypatch.setattr("app.graph_accounts.enter_person", enter_person)
    monkeypatch.setattr("app.graph_accounts.recent_entry", lambda inviter_key, email, since: state["recent"])
    monkeypatch.setattr("app.graph_accounts.entered_by", entered_by)
    monkeypatch.setattr("app.graph_accounts.resend_invitation", resend_invitation)
    monkeypatch.setattr("app.graph_accounts.withdraw", lambda key, inviter_key=None:
                        withdrawn.append((key, inviter_key)) or key == "acct:waiting")
    monkeypatch.setattr("app.routes_people.mailer.send",
                        lambda to, subject, text, **kw: sent.append((to, subject, text)) or state["send"])
    member_app.entries, member_app.sent, member_app.resent, member_app.withdrawn, member_app.state = \
        entries, sent, resent, withdrawn, state
    return member_app


def test_the_entry_form_never_fills_in_the_members_own_details(people):
    page = people.client.get("/people").text
    for field in ("name", "email", "country", "postal_code", "relationship"):
        assert re.search(rf'<(input|select) id="{field}" name="{field}"[^>]*autocomplete="off"', page), field
    assert re.search(r'<input type="checkbox" name="agreed"[^>]*autocomplete="off"', page)
    options = re.findall(r'<option value="([a-z]*)">', page)
    assert options == ["", "family", "neighbor", "friend", "work", "school", "health", "organization"]
    assert "This person has agreed to be entered" in page
    assert '<a href="/people">Enter a person</a>' in page


def test_entering_someone_sends_the_invitation_from_the_site_address(people):
    result = people.client.post("/people", data=FORM, headers={"Host": "evil.example"}, follow_redirects=False)
    entry = people.entries[0]
    assert result.status_code == 303 and result.headers["location"] == f"/people?entered={quote(entry['key'], safe='')}"
    assert entry["email"] == "bob@example.org" and entry["inviter_key"] == "acct:ada"
    assert entry["relationship"] == "neighbor" and entry["key"].startswith("acct:")
    to, subject, text = people.sent[0]
    secret = re.search(r"https://record\.example/accept/(\S+)", text).group(1)
    assert accounts.link_hash(secret) == entry["token_hash"]
    assert "Entered by: Ada Lovelace" in text and "evil.example" not in text
    page = people.client.get(result.headers["location"]).text
    assert "Bob Smith is entered. The invitation is on its way to bob@example.org. The link works for 14 days." in page
    assert secret not in page  # the link goes only in the email


def test_success_redirects_so_a_refresh_sends_nothing(people):
    """Item 14 of the 5 October review: the answer to a successful entry is a redirect, so reloading
    the page it lands on is a GET that enters and sends nothing."""
    location = people.client.post("/people", data=FORM, follow_redirects=False).headers["location"]
    for _ in range(2):
        people.client.get(location)
    assert len(people.sent) == 1 and len(people.entries) == 1


def test_names_are_cleaned_as_the_record_expects(people):
    people.client.post("/people", data={**FORM, "name": "  bob   smith. "})
    assert people.entries[0]["name"] == "Bob smith"
    assert accounts.person_name("x" * 200) == "X" + "x" * 119


@pytest.mark.parametrize("change, message", [
    ({"name": ""}, "Please fill in every field."),
    ({"country": "  "}, "Please fill in every field."),
    ({"relationship": "colleague"}, "Please fill in every field."),
    ({"agreed": ""}, "Please enter only someone who has agreed, and tick the box to say so."),
    ({"email": "bob@example"}, "That email address does not look complete. Please check it."),
])
def test_an_incomplete_entry_says_what_is_missing_and_keeps_what_was_typed(people, change, message):
    data = {**FORM, **change}
    result = people.client.post("/people", data=data)
    assert message in result.text and people.entries == [] and people.sent == []
    assert 'value="Germany"' in result.text or change.get("country")


def test_entering_an_address_twice_is_refused_without_an_email(people):
    people.state["taken"].add("bob@example.org")
    result = people.client.post("/people", data=FORM)
    assert "Someone with that email address has already been entered." in result.text
    assert people.sent == []


def test_a_double_tap_sends_once_and_promises_nothing(people):
    people.client.post("/people", data=FORM)
    people.state["recent"] = "acct:bob"
    second = people.client.post("/people", data=FORM)
    assert "Bob Smith is entered. If the invitation does not arrive, use Send the invitation again in the list below." in second.text
    assert "on its way" not in second.text
    assert len(people.sent) == 1


def test_a_double_tap_after_a_failed_send_does_not_say_on_its_way(people):
    people.state["send"] = False
    first = people.client.post("/people", data=FORM)
    assert "Bob Smith is entered, but the invitation email did not go. Please try again in a minute." in first.text
    people.state["recent"] = people.entries[0]["key"]
    second = people.client.post("/people", data=FORM)
    assert "on its way" not in second.text
    # The list carries the truth: Bob is invited, with the button to send again.
    assert "Bob Smith · neighbor" in second.text
    assert f'action="/people/{people.entries[0]["key"]}/resend"' in second.text


def test_a_failed_email_offers_to_send_again_with_a_fresh_link(people):
    people.state["send"] = False
    result = people.client.post("/people", data=FORM)
    key = people.entries[0]["key"]
    assert f'action="/people/{key}/resend"' in result.text
    people.state["send"] = True
    again = people.client.post(f"/people/{key}/resend", follow_redirects=False)
    assert again.status_code == 303 and again.headers["location"] == f"/people?resent={quote(key, safe='')}"
    assert ("A new invitation is on its way to bob@example.org. The earlier link no longer works."
            in people.client.get(again.headers["location"]).text)
    resent_key, fresh_hash, inviter = people.resent[0]
    assert resent_key == key and inviter == "acct:ada" and fresh_hash != people.entries[0]["token_hash"]


def test_sending_again_draws_on_the_limits_forgot_password_uses(people, monkeypatch):
    """Q17 and item 26: one pair of limits for every new link. The address's limit is an hour, so
    its refusal does not say "wait a minute"."""
    from app.auth import KeyedLimit
    monkeypatch.setattr("app.accounts.link_per_address", KeyedLimit(1, 3600))
    people.client.post("/people/acct:waiting/resend")
    refused = people.client.post("/people/acct:waiting/resend")
    assert refused.status_code == 429
    assert "Too many emails to that address in the last hour. Please try again later." in refused.text
    assert len(people.sent) == 1


def test_a_drained_forgot_form_does_not_block_sending_again(people, monkeypatch):
    """Second review, item 2: strangers can empty the anonymous forgot form's bucket; a member's
    button does not take from it."""
    from app.auth import MinuteBucket
    monkeypatch.setattr("app.accounts.forgot_per_minute", MinuteBucket(capacity=0, period=60))
    assert people.client.post("/people/acct:waiting/resend", follow_redirects=False).status_code == 303
    assert len(people.sent) == 1


def test_the_list_shows_who_joined_who_is_waiting_and_whose_link_expired(people):
    page = people.client.get("/people").text
    assert "Joined Person · friend · entered" in page and "joined" in page
    assert "Waiting Person · work" in page and "invited, not accepted yet" in page
    assert "Late Person · school" in page and "invitation expired" in page
    assert "Gone Person · health" in page and "switched off" in page  # switched off wins over joined
    assert page.count("Send the invitation again") == 2
    assert "If an email address was mistyped, withdraw the entry and enter the person again." in page


def test_the_list_gets_only_what_it_shows(people, monkeypatch):
    """Item 24: no email, link purpose or expiry reaches the template's list."""
    from app import routes_people
    seen = {}
    real = routes_people.page
    monkeypatch.setattr(routes_people, "page", lambda request, name, context=None, **kw:
                        seen.update(context or {}) or real(request, name, context, **kw))
    people.client.get("/people")
    assert {field for entry in seen["entries"] for field in entry} == {
        "key", "name", "relationship", "entered_at", "accepted_at", "state"}


def test_one_rule_for_the_state_of_an_entry():
    row = {"active": False, "accepted_at": NOW, "purpose": None, "expires_at": None}
    assert accounts.entry_state(row, NOW) == "switched off"
    assert accounts.entry_state({**row, "active": True}, NOW) == "joined"
    waiting = {"active": True, "accepted_at": None, "purpose": "invite", "expires_at": NOW + timedelta(seconds=1)}
    assert accounts.entry_state(waiting, NOW) == "invited"
    assert accounts.entry_state({**waiting, "expires_at": NOW}, NOW) == "expired"
    assert accounts.entry_state({**waiting, "purpose": None, "expires_at": None}, NOW) == "expired"


def test_withdrawing_asks_first_then_removes(people):
    confirm = people.client.get("/people/acct:waiting/withdraw").text
    assert "Withdraw the entry for Waiting Person? Their link stops working and the details you entered are removed." in confirm
    assert "Keep it" in confirm
    done = people.client.post("/people/acct:waiting/withdraw")
    assert "The entry for Waiting Person is withdrawn." in done.text
    assert people.withdrawn == [("acct:waiting", "acct:ada")]


def test_someone_elses_or_a_gone_entry_is_left_alone(people):
    for path in ("/people/acct:other/withdraw", "/people/acct:joined/withdraw"):
        assert people.client.get(path, follow_redirects=False).headers["location"] == "/people"
        assert people.client.post(path, follow_redirects=False).headers["location"] == "/people"
    assert people.client.post("/people/acct:other/resend", follow_redirects=False).headers["location"] == "/people"
    assert people.withdrawn == [] and people.resent == [] and people.sent == []


def test_too_many_entries_wait_a_minute(people, monkeypatch):
    from app.auth import KeyedLimit
    monkeypatch.setattr("app.accounts.entering_limit", KeyedLimit(1, 3600))
    people.client.post("/people", data=FORM)
    result = people.client.post("/people", data={**FORM, "email": "cy@example.org"})
    assert result.status_code == 429 and "Too many tries. Please wait a minute and try again." in result.text


def test_strangers_and_accounts_off(member_app, monkeypatch):
    assert member_app.client.get("/people", follow_redirects=False).headers["location"].startswith("/sign-in")
    from dataclasses import replace
    monkeypatch.setattr("app.config.get_settings", lambda: replace(member_app.settings, accounts_enabled=False))
    assert member_app.client.get("/people").status_code == 404
