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
