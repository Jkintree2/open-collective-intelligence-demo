"""X2 on the disposable Neo4j: asking, confirming, every earlier address kept with its date, an address
never given to two people, and export and restore carrying the history but never the pending link."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import accounts, graph_accounts
from app.backup import validate_record
from tests.test_live_accounts import make_account

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def person(graph, key="acct:ada"):
    return graph.driver().execute_query("MATCH (p:Person {key: $key}) RETURN properties(p) AS p", key=key,
                                        database_=graph.database()).records[0]["p"]


def ask(email, key="acct:ada", expires=NOW + timedelta(hours=24)):
    secret, token_hash = accounts.new_link()
    return graph_accounts.ask_email_change(key, email, token_hash, expires), token_hash


def test_the_email_moves_only_when_the_link_is_opened_and_the_old_one_is_kept(live_graph):
    make_account(live_graph)
    row, link = ask("ada.new@example.org")
    assert row == {"name": "Ada Tester", "email": "ada@example.org"}
    assert person(live_graph)["email"] == "ada@example.org"
    assert graph_accounts.open_link(link)["pending_email"] == "ada.new@example.org"
    assert graph_accounts.confirm_email_change(link, NOW) == {"key": "acct:ada", "free": True,
                                                              "old": "ada@example.org", "new": "ada.new@example.org"}
    after = person(live_graph)
    assert after["email"] == "ada.new@example.org"
    assert after["previous_emails"] == ["ada@example.org"]
    assert [until.to_native() for until in after["previous_emails_until"]] == [NOW]
    assert not {"token_hash", "token_purpose", "token_expires_at", "pending_email"} & set(after)
    assert graph_accounts.confirm_email_change(link, NOW) is None  # works once
    assert graph_accounts.sign_in_row("ada.new@example.org")["key"] == "acct:ada"
    assert graph_accounts.sign_in_row("ada@example.org") is None
    # A second change adds to the history, oldest first.
    _, link = ask("ada.third@example.org")
    graph_accounts.confirm_email_change(link, NOW + timedelta(hours=1))
    assert person(live_graph)["previous_emails"] == ["ada@example.org", "ada.new@example.org"]


def test_an_address_another_account_has_or_had_is_never_given(live_graph):
    make_account(live_graph)
    make_account(live_graph, key="acct:bob", email="bob@example.org")
    assert ask("bob@example.org")[0] is None
    assert ask("ada@example.org")[0] is None  # already hers
    _, link = ask("bob.new@example.org", key="acct:bob")
    graph_accounts.confirm_email_change(link, NOW)
    assert ask("bob@example.org")[0] is None  # Bob's earlier address stays his
    with pytest.raises(graph_accounts.EmailTaken):
        graph_accounts.enter_person(inviter_key="acct:ada", key="acct:new", name="New", email="bob@example.org",
                                    country="UK", postal_code="", relationship="friend", token_hash="t",
                                    expires_at=NOW + timedelta(days=14), now=NOW)


def test_an_address_taken_meanwhile_uses_the_link_and_changes_nothing(live_graph):
    make_account(live_graph)
    _, link = ask("shared@example.org")
    make_account(live_graph, key="acct:bob", email="shared@example.org")
    result = graph_accounts.confirm_email_change(link, NOW)
    assert result["free"] is False
    after = person(live_graph)
    assert after["email"] == "ada@example.org" and "previous_emails" not in after and "token_hash" not in after


def test_an_expired_link_does_nothing(live_graph):
    make_account(live_graph)
    _, link = ask("ada.new@example.org", expires=NOW - timedelta(minutes=1))
    assert graph_accounts.confirm_email_change(link, NOW) is None
    assert person(live_graph)["email"] == "ada@example.org"


def test_export_and_restore_keep_the_history_and_never_the_pending_link(live_graph):
    make_account(live_graph)
    _, link = ask("ada.new@example.org")
    graph_accounts.confirm_email_change(link, NOW)
    ask("ada.third@example.org")  # pending, never in a copy
    exported = json.loads(json.dumps(live_graph.export_record()))
    assert "ada.third" not in json.dumps(exported)
    validate_record(exported)
    before = {k: v for k, v in person(live_graph).items() if k not in ("password_hash", "token_hash", "token_purpose",
                                                                        "token_expires_at", "pending_email")}
    live_graph.driver().execute_query("MATCH (n) DETACH DELETE n", database_=live_graph.database())
    live_graph.restore_record(exported)
    assert person(live_graph) == before
