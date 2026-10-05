from datetime import datetime, timedelta, timezone

import pytest
from neo4j.exceptions import ConstraintError

from app import graph_accounts

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)

ACCOUNT = """
CREATE (p:Person {key: $key, name: $name, anonymous: false, seed: false, email: $email,
                  password_hash: $password_hash, admin: false, active: $active, created_at: $now,
                  accepted_at: $accepted_at})
"""


def make_account(graph, key="acct:ada", email="ada@example.org", *, accepted=True, active=True):
    graph.driver().execute_query(ACCOUNT, key=key, name="Ada Tester", email=email,
                                 password_hash="scrypt$x" if accepted else None, active=active, now=NOW,
                                 accepted_at=NOW if accepted else None, database_=graph.database())


def test_only_an_accepted_active_account_is_a_member(live_graph):
    make_account(live_graph)
    make_account(live_graph, "acct:bob", "bob@example.org", accepted=False)
    make_account(live_graph, "acct:cy", "cy@example.org", active=False)
    assert graph_accounts.member("acct:ada")["email"] == "ada@example.org"
    assert graph_accounts.member("acct:bob") is None
    assert graph_accounts.member("acct:cy") is None
    assert graph_accounts.sign_in_row("bob@example.org")["accepted_at"] is None


def test_one_account_per_email(live_graph):
    make_account(live_graph)
    with pytest.raises(ConstraintError):
        make_account(live_graph, "acct:other", "ada@example.org")


CLAIM = """
MERGE (p:Person {key: $person})
ON CREATE SET p.name = $name, p.anonymous = $anonymous_person
MERGE (i:Issue {key: 'flooding'}) ON CREATE SET i.name = 'Flooding'
CREATE (p)-[:CLAIM {post_id: $post, anonymous: $anonymous, created_at: $now}]->(i)
"""


OLD_CLAIMANTS = """
MATCH (p:Person)-[c:CLAIM]->(i:Issue {key: $key})
RETURN count(c) AS claims, count(DISTINCT p) AS people,
       collect(DISTINCT CASE WHEN c.anonymous THEN 'Anonymous' ELSE p.name END) AS names
"""  # the 0.1 statement (commit 62a6727)


def claim_runner(live_graph):
    return lambda **p: live_graph.driver().execute_query(CLAIM, now=NOW, database_=live_graph.database(), **p)


def test_claimants_count_old_people_and_accounts_by_identity(live_graph):
    """D2: an account's named and anonymous claims count apart; 0.1 people keep their numbers."""
    run = claim_runner(live_graph)
    run(person="name:grace", name="Grace", anonymous_person=False, post="p1", anonymous=False)
    run(person="anon:1", name=None, anonymous_person=True, post="p2", anonymous=True)
    run(person="acct:ada", name="Ada Tester", anonymous_person=False, post="p3", anonymous=False)
    run(person="acct:ada", name="Ada Tester", anonymous_person=False, post="p4", anonymous=True)
    claimants = live_graph.issue_claimants("flooding")
    assert claimants["people"] == 4 and claimants["claims"] == 4
    assert sorted(claimants["names"]) == ["Ada Tester", "Anonymous", "Grace"]


def test_an_account_with_a_named_and_an_anonymous_claim_reads_as_two_people(live_graph):
    run = claim_runner(live_graph)
    run(person="acct:ada", name="Ada Tester", anonymous_person=False, post="p1", anonymous=False)
    run(person="acct:ada", name="Ada Tester", anonymous_person=False, post="p2", anonymous=True)
    claimants = live_graph.issue_claimants("flooding")
    assert claimants["people"] == 2 and claimants["claims"] == 2
    assert sorted(claimants["names"]) == ["Ada Tester", "Anonymous"]


def test_two_anonymous_claims_by_one_account_count_once_as_anonymous(live_graph):
    run = claim_runner(live_graph)
    run(person="acct:ada", name="Ada Tester", anonymous_person=False, post="p1", anonymous=True)
    run(person="acct:ada", name="Ada Tester", anonymous_person=False, post="p2", anonymous=True)
    claimants = live_graph.issue_claimants("flooding")
    assert claimants["people"] == 1 and claimants["claims"] == 2
    assert claimants["names"] == ["Anonymous"]


def test_a_01_record_reads_the_same_as_under_the_01_statement(live_graph):
    run = claim_runner(live_graph)
    run(person="name:grace", name="Grace", anonymous_person=False, post="p1", anonymous=False)
    run(person="name:grace", name="Grace", anonymous_person=False, post="p2", anonymous=False)
    run(person="name:hal", name="Hal", anonymous_person=False, post="p3", anonymous=None)
    run(person="anon:1", name=None, anonymous_person=True, post="p4", anonymous=True)
    run(person="anon:2", name=None, anonymous_person=True, post="p5", anonymous=True)
    old, _, _ = live_graph.driver().execute_query(OLD_CLAIMANTS, key="flooding", database_=live_graph.database())
    new = live_graph.issue_claimants("flooding")
    assert (new["claims"], new["people"], sorted(new["names"])) == \
        (old[0]["claims"], old[0]["people"], sorted(old[0]["names"])) == (5, 4, ["Anonymous", "Grace", "Hal"])


def test_a_claim_with_no_anonymous_property_is_listed_by_name(live_graph):
    """collect() drops nulls; a claim edge without the property must still count as named (as in 0.1)."""
    run = claim_runner(live_graph)
    run(person="name:grace", name="Grace", anonymous_person=False, post="p1", anonymous=None)
    run(person="name:hal", name="Hal", anonymous_person=False, post="p2", anonymous=None)
    run(person="name:hal", name="Hal", anonymous_person=False, post="p3", anonymous=True)
    claimants = live_graph.issue_claimants("flooding")
    assert claimants["people"] == 3 and claimants["claims"] == 3
    assert sorted(claimants["names"]) == ["Anonymous", "Grace", "Hal"]


def test_setting_a_password_clears_a_pending_link(live_graph):
    make_account(live_graph)
    live_graph.driver().execute_query(
        "MATCH (p:Person {key: 'acct:ada'}) SET p.token_hash = 'h', p.token_purpose = 'reset', p.token_expires_at = $now",
        now=NOW, database_=live_graph.database())
    graph_accounts.set_password("acct:ada", "scrypt$new")
    row = live_graph.driver().execute_query("MATCH (p:Person {key: 'acct:ada'}) RETURN p.token_hash AS t, p.password_hash AS h",
                                            database_=live_graph.database()).records[0]
    assert row["t"] is None and row["h"] == "scrypt$new"


def test_who_entered_names_the_inviter_and_the_relationship(live_graph):
    make_account(live_graph)
    make_account(live_graph, "acct:bob", "bob@example.org")
    live_graph.driver().execute_query(
        "MATCH (a:Person {key: 'acct:ada'}), (b:Person {key: 'acct:bob'}) "
        "CREATE (a)-[:ENTERED {relationship: 'friend', agreed: true, created_at: $now}]->(b)",
        now=NOW, database_=live_graph.database())
    row = graph_accounts.who_entered("acct:bob")
    assert row["inviter_name"] == "Ada Tester" and row["relationship"] == "friend"
    assert row["entered_at"] == NOW
    assert graph_accounts.who_entered("acct:ada") is None  # the root has no entry


def test_forgot_gives_an_account_a_reset_link_and_an_invited_person_an_invitation(live_graph):
    make_account(live_graph)
    make_account(live_graph, "acct:bob", "bob@example.org", accepted=False)
    make_account(live_graph, "acct:cy", "cy@example.org", active=False)
    later, soon = NOW + timedelta(days=14), NOW + timedelta(hours=1)
    assert graph_accounts.forgot("ada@example.org", "h1", later, soon)["purpose"] == "reset"
    assert graph_accounts.forgot("bob@example.org", "h2", later, soon)["purpose"] == "invite"
    assert graph_accounts.forgot("cy@example.org", "h3", later, soon) is None
    assert graph_accounts.forgot("nobody@example.org", "h4", later, soon) is None
    assert graph_accounts.reset_password("h2", "scrypt$x", NOW) is None   # an invitation is not a reset
    assert graph_accounts.reset_password("h1", "scrypt$new", NOW) == "acct:ada"
    assert graph_accounts.reset_password("h1", "scrypt$again", NOW) is None  # used once


def test_the_root_account_gets_its_first_link_through_forgot(live_graph):
    """X3: make_admin.py made the root with no link and no ENTERED; Forgot gives it an invitation."""
    graph_accounts.create_root(key="acct:john", name="John Kintree", email="john@example.org",
                               country="", postal_code="", now=NOW)
    later, soon = NOW + timedelta(days=14), NOW + timedelta(hours=1)
    row = graph_accounts.forgot("john@example.org", "root-link", later, soon)
    assert row == {"email": "john@example.org", "name": "John Kintree", "purpose": "invite",
                   "inviter_name": None, "relationship": None}
    assert graph_accounts.accept("root-link", name="John Kintree", country="USA", postal_code="98101",
                                 password_hash="scrypt$john", now=NOW) == "acct:john"
    assert graph_accounts.member("acct:john")["admin"] is True


def test_an_expired_or_unaccepted_link_does_not_reset(live_graph):
    """Q18 checks the purpose, the hour and that the account is accepted."""
    make_account(live_graph)
    graph_accounts.forgot("ada@example.org", "h1", NOW + timedelta(days=14), NOW + timedelta(hours=1))
    assert graph_accounts.reset_password("h1", "scrypt$late", NOW + timedelta(hours=2)) is None
    assert graph_accounts.reset_password("h1", "scrypt$ok", NOW + timedelta(minutes=30)) == "acct:ada"
