import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import graph_accounts
from app.graph_accounts import EmailTaken

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=14)


def root(graph):
    """John's root account, accepted. make_admin.py makes it with no link (X3); in the app his first
    link comes from "Forgot your password?" (A8), so here the test gives it one directly."""
    graph_accounts.create_root(key="acct:john", name="John Kintree", email="john@example.org", country="USA",
                               postal_code="98101", now=NOW)
    graph.driver().execute_query(
        "MATCH (p:Person {key: 'acct:john'}) SET p.token_hash = 'root-link', p.token_purpose = 'invite', "
        "p.token_expires_at = $later", later=LATER, database_=graph.database())
    assert graph_accounts.accept("root-link", name="John Kintree", country="USA", postal_code="98101",
                                 password_hash="scrypt$john", now=NOW) == "acct:john"


def test_the_root_is_made_without_a_link_and_cannot_sign_in_yet(live_graph):
    graph_accounts.create_root(key="acct:john", name="John Kintree", email="john@example.org", country="",
                               postal_code="", now=NOW)
    row = live_graph.driver().execute_query(
        "MATCH (p:Person {key: 'acct:john'}) RETURN p.token_hash AS t, p.admin AS admin, p.accepted_at AS a",
        database_=live_graph.database()).records[0]
    assert row["t"] is None and row["admin"] is True and row["a"] is None
    assert graph_accounts.member("acct:john") is None
    with pytest.raises(EmailTaken):
        graph_accounts.create_root(key="acct:other", name="John Kintree", email="john@example.org", country="",
                                   postal_code="", now=NOW)


def test_sending_again_to_the_root_names_no_inviter(live_graph):
    """X3: the back room's re-send (sub-plan F) reaches a root that has not accepted yet."""
    graph_accounts.create_root(key="acct:john", name="John Kintree", email="john@example.org", country="",
                               postal_code="", now=NOW)
    assert graph_accounts.resend_invitation("acct:john", "fresh-root-link", LATER) == {
        "email": "john@example.org", "name": "John Kintree", "inviter_name": None, "relationship": None}
    assert graph_accounts.open_link("fresh-root-link")["inviter_name"] is None


def enter(email="bob@example.org", token="bob-link", inviter="acct:john", key="acct:bob", expires=LATER):
    return graph_accounts.enter_person(inviter_key=inviter, key=key, name="Bob Smith", email=email,
                                       country="Germany", postal_code="10115", relationship="neighbor",
                                       token_hash=token, expires_at=expires, now=NOW)


def test_entering_makes_an_invited_person_and_who_entered_them(live_graph):
    root(live_graph)
    assert enter() is True
    row = graph_accounts.open_link("bob-link")
    assert row["purpose"] == "invite" and row["accepted_at"] is None and row["inviter_name"] == "John Kintree"
    assert row["relationship"] == "neighbor" and row["country"] == "Germany"
    assert graph_accounts.member("acct:bob") is None  # cannot sign in yet
    entered = live_graph.driver().execute_query(
        "MATCH (:Person {key: 'acct:john'})-[e:ENTERED]->(:Person {key: 'acct:bob'}) RETURN e.agreed AS agreed",
        database_=live_graph.database()).records
    assert [r["agreed"] for r in entered] == [True]


def test_only_an_accepted_member_can_enter(live_graph):
    root(live_graph)
    enter()
    assert enter(email="cy@example.org", token="cy-link", inviter="acct:bob", key="acct:cy") is False
    assert graph_accounts.open_link("cy-link") is None


def test_one_account_per_email_even_when_entered_twice(live_graph):
    root(live_graph)
    enter()
    with pytest.raises(EmailTaken):
        enter(token="second-link", key="acct:bob2")
    assert graph_accounts.recent_entry("acct:john", "bob@example.org", NOW - timedelta(seconds=60)) == "acct:bob"
    assert graph_accounts.recent_entry("acct:john", "bob@example.org", NOW + timedelta(seconds=1)) is None
    labels, _ = live_graph.counts()
    assert labels["Person"] == 2


def test_accepting_sets_the_password_and_works_once(live_graph):
    root(live_graph)
    enter()
    key = graph_accounts.accept("bob-link", name="Robert Smith", country="Germany", postal_code="10117",
                                password_hash="scrypt$bob", now=NOW)
    assert key == "acct:bob"
    assert graph_accounts.member("acct:bob")["name"] == "Robert Smith"
    assert graph_accounts.open_link("bob-link") is None
    assert graph_accounts.accept("bob-link", name="X", country="X", postal_code="X",
                                 password_hash="scrypt$again", now=NOW) is None


def test_an_expired_invitation_cannot_be_accepted(live_graph):
    root(live_graph)
    enter(expires=NOW - timedelta(seconds=1))
    assert graph_accounts.accept("bob-link", name="Bob", country="G", postal_code="1",
                                 password_hash="scrypt$bob", now=NOW) is None


def test_sending_again_replaces_the_link(live_graph):
    root(live_graph)
    enter()
    sent = graph_accounts.resend_invitation("acct:bob", "fresh-link", LATER, inviter_key="acct:john")
    assert sent == {"email": "bob@example.org", "name": "Bob Smith", "inviter_name": "John Kintree",
                    "relationship": "neighbor"}
    assert graph_accounts.open_link("bob-link") is None and graph_accounts.open_link("fresh-link")
    assert graph_accounts.resend_invitation("acct:bob", "x", LATER, inviter_key="acct:someone") is None
    graph_accounts.accept("fresh-link", name="Bob", country="G", postal_code="1", password_hash="scrypt$b", now=NOW)
    assert graph_accounts.resend_invitation("acct:bob", "y", LATER, inviter_key="acct:john") is None


def waits_then(live_graph, hold, query, **params):
    """Run `hold` (and its params) in a transaction left open, start `query` in a thread, check it
    waits for the lock, commit, and return what the thread got (C1's held transaction style)."""
    session = live_graph.driver().session(database=live_graph.database())
    held = session.begin_transaction()
    held.run(hold, **params).consume()
    done = []
    thread = threading.Thread(target=lambda: done.append(query()))
    thread.start()
    thread.join(timeout=1.0)
    try:
        assert thread.is_alive() and done == []  # waiting for the lock
    finally:
        held.commit()
        session.close()
    thread.join(timeout=15)
    return done


def test_a_withdrawal_waits_for_an_accept_in_progress_and_leaves_the_account(live_graph):
    """Second review, item 1: without the lock taken first, the withdrawal would have read the
    person as not accepted, then deleted the account the accept had just made."""
    root(live_graph)
    enter()
    done = waits_then(live_graph, "MATCH (p:Person {key: 'acct:bob'}) SET p.key = p.key, p.accepted_at = $now, "
                                  "p.password_hash = 'scrypt$bob', p.token_hash = null", lambda: graph_accounts.withdraw(
                                      "acct:bob", inviter_key="acct:john"), now=NOW)
    assert done == [False]
    assert graph_accounts.member("acct:bob") is not None


def test_sending_again_waits_for_a_withdrawal_and_finds_nothing(live_graph):
    """The other way round: the withdrawal wins, and the re-send that waited for it answers None
    (the page then goes back to the list), never a server error."""
    root(live_graph)
    enter()
    done = waits_then(live_graph, "MATCH (p:Person {key: 'acct:bob'}) DETACH DELETE p",
                      lambda: graph_accounts.resend_invitation("acct:bob", "fresh-link", LATER, inviter_key="acct:john"))
    assert done == [None]


def test_two_accepts_on_one_link_succeed_once(live_graph):
    """Second review, item 1: the second tab's accept waits, then finds the link used; it does not
    overwrite the first tab's name and password (which would also sign the first tab out)."""
    root(live_graph)
    enter()
    done = waits_then(live_graph, graph_accounts.ACCEPT, lambda: graph_accounts.accept(
        "bob-link", name="Bob Two", country="G", postal_code="1", password_hash="scrypt$two", now=NOW),
        token_hash="bob-link", name="Bob One", country="G", postal_code="1", password_hash="scrypt$one", now=NOW)
    assert done == [None]
    assert graph_accounts.member("acct:bob")["name"] == "Bob One"
    assert graph_accounts.member("acct:bob")["password_hash"] == "scrypt$one"


def test_withdrawing_removes_only_a_never_accepted_entry_by_its_inviter(live_graph):
    root(live_graph)
    enter()
    enter(email="cy@example.org", token="cy-link", key="acct:cy")
    graph_accounts.accept("cy-link", name="Cy", country="G", postal_code="1", password_hash="scrypt$c", now=NOW)
    assert [row["key"] for row in graph_accounts.entered_by("acct:john")] in (["acct:cy", "acct:bob"], ["acct:bob", "acct:cy"])
    assert graph_accounts.withdraw("acct:bob", inviter_key="acct:someone") is False
    assert graph_accounts.withdraw("acct:cy", inviter_key="acct:john") is False   # accepted: switch off instead
    assert graph_accounts.withdraw("acct:bob", inviter_key="acct:john") is True
    assert graph_accounts.open_link("bob-link") is None
    assert [row["key"] for row in graph_accounts.entered_by("acct:john")] == ["acct:cy"]
