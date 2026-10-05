from datetime import datetime, timezone

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
    graph.driver().execute_query(ACCOUNT, key=key, name="Ada Lovelace", email=email,
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


def test_claimants_count_old_people_and_accounts_once(live_graph):
    """Review Focus 1: 0.1 people keep their posts; an account with named and anonymous claims is one
    person, listed once by name; anonymous 0.1 people are listed as Anonymous."""
    run = lambda **p: live_graph.driver().execute_query(CLAIM, now=NOW, database_=live_graph.database(), **p)
    run(person="name:grace", name="Grace", anonymous_person=False, post="p1", anonymous=False)
    run(person="anon:1", name=None, anonymous_person=True, post="p2", anonymous=True)
    run(person="acct:ada", name="Ada Lovelace", anonymous_person=False, post="p3", anonymous=False)
    run(person="acct:ada", name="Ada Lovelace", anonymous_person=False, post="p4", anonymous=True)
    claimants = live_graph.issue_claimants("flooding")
    assert claimants["people"] == 3 and claimants["claims"] == 4
    assert sorted(claimants["names"]) == ["Ada Lovelace", "Anonymous", "Grace"]


def test_a_person_with_named_and_anonymous_claims_is_listed_only_by_name(live_graph):
    """The old rule listed such a person twice, once by name and once as Anonymous."""
    run = lambda **p: live_graph.driver().execute_query(CLAIM, now=NOW, database_=live_graph.database(), **p)
    run(person="acct:ada", name="Ada Lovelace", anonymous_person=False, post="p1", anonymous=False)
    run(person="acct:ada", name="Ada Lovelace", anonymous_person=False, post="p2", anonymous=True)
    claimants = live_graph.issue_claimants("flooding")
    assert claimants["people"] == 1 and claimants["claims"] == 2
    assert claimants["names"] == ["Ada Lovelace"]


def test_a_claim_with_no_anonymous_property_is_listed_by_name(live_graph):
    """collect() drops nulls; a claim edge without the property must still count as named (as in 0.1)."""
    run = lambda **p: live_graph.driver().execute_query(CLAIM, now=NOW, database_=live_graph.database(), **p)
    run(person="name:grace", name="Grace", anonymous_person=False, post="p1", anonymous=None)
    run(person="name:hal", name="Hal", anonymous_person=False, post="p2", anonymous=None)
    run(person="name:hal", name="Hal", anonymous_person=False, post="p3", anonymous=True)
    claimants = live_graph.issue_claimants("flooding")
    assert claimants["people"] == 2 and claimants["claims"] == 3
    assert sorted(claimants["names"]) == ["Grace", "Hal"]
