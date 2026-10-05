"""One Phase 1 record, downloaded and put back into an empty database (03_schema.md Q33): what
Phase 1 adds comes back exactly, nothing secret leaves, and a restored account chooses a new
password by link. Live: the disposable test Neo4j only."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import accounts, graph_accounts

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)

RECORD = """
CREATE (john:Person {key: 'acct:john', name: 'John Kintree', anonymous: false, seed: false,
        email: 'john@example.org', country: 'USA', postal_code: '98101', admin: true, active: true,
        created_at: $now, accepted_at: $now, password_hash: 'scrypt$john-secret'})
CREATE (ada:Person {key: 'acct:ada', name: 'Ada Lovelace', anonymous: false, seed: false,
        email: 'ada@example.org', country: 'UK', postal_code: 'N1', admin: false, active: true,
        created_at: $now, accepted_at: $now, password_hash: 'scrypt$ada-secret',
        token_hash: 'pending-reset', token_purpose: 'reset', token_expires_at: $later})
CREATE (bob:Person {key: 'acct:bob', name: 'Bob Smith', anonymous: false, seed: false,
        email: 'bob@example.org', country: 'Germany', postal_code: '10115', admin: false, active: true,
        created_at: $now, token_hash: 'pending-invite', token_purpose: 'invite', token_expires_at: $later})
CREATE (grace:Person {key: 'name:grace', name: 'Grace', anonymous: false, seed: false, created_at: $now})
CREATE (john)-[:ENTERED {relationship: 'friend', agreed: true, created_at: $now}]->(ada)
CREATE (ada)-[:ENTERED {relationship: 'neighbor', agreed: true, created_at: $now}]->(bob)
CREATE (i:Issue {key: 'building a platform for digital democracy',
                 name: 'Building a platform for digital democracy', seed: false, created_at: $now})
CREATE (sub:Issue {key: 'open meetings online', name: 'Open meetings online', seed: false, created_at: $now})
CREATE (sub)-[:PART_OF {created_at: $now}]->(i)
CREATE (s:Solution {key: 'public minutes', name: 'Public minutes', seed: false, created_at: $now})
CREATE (i)-[:HAVE_PROPOSED {post_id: '6f1c2d3e-8a47-4b5e-9c10-2d7e4f9a1b30', created_at: $now}]->(s)
CREATE (post:Post {id: '6f1c2d3e-8a47-4b5e-9c10-2d7e4f9a1b30', text: 'Meetings should publish their minutes', created_at: $now,
                   edited_at: $later, anonymous: false, display_name: 'Ada Lovelace', source: 'manual',
                   seed: false, payload: '{}'})
CREATE (ada)-[:POSTED {post_id: '6f1c2d3e-8a47-4b5e-9c10-2d7e4f9a1b30', created_at: $now, anonymous: false}]->(post)
CREATE (ada)-[:CLAIM {post_id: '6f1c2d3e-8a47-4b5e-9c10-2d7e4f9a1b30', created_at: $now, anonymous: false}]->(i)
CREATE (ada)-[:PROPOSE {post_id: '6f1c2d3e-8a47-4b5e-9c10-2d7e4f9a1b30', created_at: $now, anonymous: false}]->(s)
CREATE (john)-[:APPROVE {source: 'click', anonymous: false, created_at: $now}]->(s)
CREATE (grace)-[:OPPOSE {post_id: '0b9e5a72-3c1d-4e68-a4f7-81d6c2e95b14', anonymous: false, created_at: $now}]->(s)
CREATE (c:Change {id: 'change-1', kind: 'rename', created_at: $now, details: $details})
CREATE (john)-[:MADE {created_at: $now}]->(c)
CREATE (c)-[:CHANGED {created_at: $now}]->(i)
"""
DETAILS = json.dumps({"from_key": "platform for digital democracy", "from_name": "Platform for digital democracy",
                      "to_key": "building a platform for digital democracy",
                      "to_name": "Building a platform for digital democracy"})


def run(graph, query, **params):
    graph.driver().execute_query(query, params, database_=graph.database())


def copied(graph):
    run(graph, RECORD, now=NOW, later=NOW + timedelta(days=1), details=DETAILS)
    return json.loads(json.dumps(graph.export_record()))


def put_back(graph, exported):
    run(graph, "MATCH (n) DETACH DELETE n")
    return graph.restore_record(exported)


def test_a_copy_keeps_everything_phase_1_adds_and_no_secret(live_graph):
    exported = copied(live_graph)
    text = json.dumps(exported)
    for secret in ("scrypt$", "pending-reset", "pending-invite", "password_hash", "token_hash",
                   "token_purpose", "token_expires_at"):
        assert secret not in text, secret
    assert exported["version"] == 2
    assert {"ENTERED", "MADE", "CHANGED", "APPROVE", "OPPOSE", "PART_OF"} <= {r["type"] for r in exported["relationships"]}
    clicks = [r for r in exported["relationships"] if r["properties"].get("source") == "click"]
    assert len(clicks) == 1 and "post_id" not in clicks[0]["properties"]
    tidied = [r for r in exported["relationships"] if r["type"] == "PART_OF"]
    assert "post_id" not in tidied[0]["properties"]
    post = next(n for n in exported["nodes"] if n["label"] == "Post")
    assert post["properties"]["edited_at"]["$type"] == "DateTime"
    before = live_graph.counts()

    assert put_back(live_graph, exported) == (len(exported["nodes"]), len(exported["relationships"]))
    assert json.loads(json.dumps(live_graph.export_record())) == exported
    assert live_graph.counts() == before


def test_a_restored_account_chooses_a_new_password_by_link(live_graph):
    put_back(live_graph, copied(live_graph))
    # Accepted and active, but no password: every cookie fails, and sign in cannot match.
    assert graph_accounts.member("acct:ada")["password_hash"] is None
    assert graph_accounts.sign_in_row("ada@example.org")["password_hash"] is None
    assert graph_accounts.open_link("pending-reset") is None and graph_accounts.open_link("pending-invite") is None
    now = datetime.now(timezone.utc)
    later, soon = accounts.link_expiry("invite", now), accounts.link_expiry("reset", now)
    assert graph_accounts.forgot("ada@example.org", "fresh-ada", later, soon)["purpose"] == "reset"
    assert graph_accounts.reset_password("fresh-ada", "scrypt$new", now) == "acct:ada"
    # Bob never accepted: "Forgot your password?" sends him a fresh invitation.
    assert graph_accounts.forgot("bob@example.org", "fresh-bob", later, soon)["purpose"] == "invite"
