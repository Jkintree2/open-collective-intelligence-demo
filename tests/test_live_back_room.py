"""The back room's account statements (03_schema.md Q17 by key, Q20 and Q21 back room versions,
Q22). Live: the disposable test Neo4j only. Accounts are made with plain Cypher, as Q12, Q16 and
make_admin leave them, so these tests do not depend on how make_admin makes the first account."""

from datetime import datetime, timedelta, timezone

import pytest

from app import graph_accounts

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=14)

ACCOUNT = """
CREATE (:Person {key: $key, name: $name, anonymous: false, seed: false, email: $email,
                 country: 'X', postal_code: '1', admin: $admin, active: true, created_at: $created,
                 accepted_at: $accepted_at, password_hash: $password_hash,
                 token_hash: $token_hash, token_purpose: $purpose, token_expires_at: $expires_at})
"""
ENTERED = """
MATCH (a:Person {key: $inviter}), (b:Person {key: $key})
CREATE (a)-[:ENTERED {relationship: $relationship, agreed: true, created_at: $created}]->(b)
"""


def run(graph, query, **params):
    graph.driver().execute_query(query, params, database_=graph.database())


def account(graph, key, name, *, accepted=True, admin=False, link=None, created=NOW, inviter=None,
            relationship=None):
    """`link` is (token_hash, purpose); the email is the key's tail at example.org."""
    run(graph, ACCOUNT, key=key, name=name, email=f"{key[5:]}@example.org", admin=admin, created=created,
        accepted_at=created if accepted else None, password_hash="scrypt$x" if accepted else None,
        token_hash=link[0] if link else None, purpose=link[1] if link else None,
        expires_at=LATER if link else None)
    if inviter:
        run(graph, ENTERED, inviter=inviter, key=key, relationship=relationship, created=created)


def people(graph, *, john_accepted=True):
    account(graph, "acct:john", "John Kintree", admin=True, accepted=john_accepted)
    account(graph, "acct:ada", "Ada Lovelace", inviter="acct:john", relationship="friend",
            created=NOW + timedelta(hours=1))
    account(graph, "acct:bob", "Bob Smith", accepted=False, link=("bob-invite", "invite"),
            inviter="acct:ada", relationship="neighbor", created=NOW + timedelta(hours=2))
    # A Person from the test weeks: no email, so not an account.
    run(graph, "CREATE (:Person {key: 'name:grace', name: 'Grace', anonymous: false, seed: false, created_at: $now})",
        now=NOW)


def test_the_back_room_lists_every_account_and_who_entered_it(live_graph):
    people(live_graph)
    rows = graph_accounts.all_accounts()
    assert [row["key"] for row in rows] == ["acct:john", "acct:bob", "acct:ada"]
    john, bob, ada = rows
    assert (john["inviter_name"], john["relationship"], john["entered_at"], john["admin"]) == (None, None, None, True)
    assert (bob["inviter_name"], bob["relationship"], bob["accepted_at"]) == ("Ada Lovelace", "neighbor", None)
    assert (bob["purpose"], bob["expires_at"]) == ("invite", LATER)
    assert ada["inviter_name"] == "John Kintree" and ada["entered_at"] == NOW + timedelta(hours=1)
    assert ada["active"] is True and ada["admin"] is False and ada["email"] == "ada@example.org"


def test_a_password_link_goes_only_to_an_accepted_active_account(live_graph):
    people(live_graph)
    sent = graph_accounts.password_link("acct:ada", "ada-reset", LATER)
    assert sent == {"email": "ada@example.org", "name": "Ada Lovelace"}
    assert graph_accounts.open_link("ada-reset")["purpose"] == "reset"
    assert graph_accounts.password_link("acct:bob", "bob-reset", LATER) is None   # not accepted: invite again instead
    assert graph_accounts.open_link("bob-invite")["purpose"] == "invite"          # and his invitation still works
    assert graph_accounts.password_link("name:grace", "grace-reset", LATER) is None
    assert graph_accounts.set_active("acct:ada", False) is True
    assert graph_accounts.password_link("acct:ada", "ada-again", LATER) is None   # switched off


def test_switching_off_signs_out_and_never_touches_the_first_account(live_graph):
    people(live_graph)
    assert graph_accounts.set_active("acct:ada", False) is True
    assert graph_accounts.member("acct:ada") is None                     # Q13: signed out on the next page
    assert graph_accounts.sign_in_row("ada@example.org")["active"] is False
    assert graph_accounts.set_active("acct:ada", True) is True
    assert graph_accounts.member("acct:ada")["name"] == "Ada Lovelace"
    assert graph_accounts.set_active("acct:john", False) is False        # John's own account, never
    assert graph_accounts.member("acct:john")["admin"] is True
    for key in ("name:grace", "acct:nobody"):
        assert graph_accounts.set_active(key, False) is False


def test_the_back_room_sends_johns_own_invitation_again_and_never_withdraws_him(live_graph):
    people(live_graph, john_accepted=False)   # between make_admin and John's first password (X3)
    sent = graph_accounts.resend_invitation("acct:john", "john-invite", LATER)
    assert sent["email"] == "john@example.org" and sent["name"] == "John Kintree"
    assert sent["inviter_name"] is None and sent["relationship"] is None
    assert graph_accounts.open_link("john-invite")["purpose"] == "invite"
    assert graph_accounts.withdraw("acct:john") is False    # nobody entered him
    assert graph_accounts.withdraw("acct:ada") is False     # accepted: switch off instead
    assert graph_accounts.resend_invitation("acct:ada", "ada-invite", LATER) is None   # accepted: no invitation
    assert graph_accounts.open_link("ada-invite") is None
    assert graph_accounts.withdraw("acct:bob") is True      # any entry never accepted, whoever made it
    assert graph_accounts.open_link("bob-invite") is None
    assert [row["key"] for row in graph_accounts.all_accounts()] == ["acct:john", "acct:ada"]
