import threading
from datetime import datetime, timezone

import pytest

from app import graph_stances

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

SETUP = """
CREATE (:Person {key: 'acct:ada', name: 'Ada', anonymous: false, email: 'ada@example.org', active: true, accepted_at: $now})
CREATE (:Person {key: 'name:grace', name: 'Grace', anonymous: false})
CREATE (i:Issue {key: 'veto', name: 'Veto', seed: false})
CREATE (s:Solution {key: 'abolish', name: 'Abolish the veto', seed: false})
CREATE (i)-[:HAVE_PROPOSED {created_at: $now}]->(s)
"""


def run(graph, query, **params):
    return graph.driver().execute_query(query, now=NOW, database_=graph.database(), **params).records


def stances(graph, person="acct:ada"):
    rows = run(graph, "MATCH (:Person {key: $p})-[r:APPROVE|OPPOSE]->(:Solution {key: 'abolish'}) "
                      "RETURN type(r) AS t, r.source AS source, r.post_id AS post_id", p=person)
    return [(row["t"], row["source"], row["post_id"]) for row in rows]


def test_approve_then_oppose_then_withdraw(live_graph):
    run(live_graph, SETUP)
    assert graph_stances.set_stance("acct:ada", "abolish", "approve", NOW) == {"approves": 1, "opposes": 0, "my_stance": "APPROVE"}
    assert stances(live_graph) == [("APPROVE", "click", None)]
    assert graph_stances.set_stance("acct:ada", "abolish", "oppose", NOW) == {"approves": 0, "opposes": 1, "my_stance": "OPPOSE"}
    assert stances(live_graph) == [("OPPOSE", "click", None)]
    assert graph_stances.set_stance("acct:ada", "abolish", "oppose", NOW)["opposes"] == 1  # pressing again is idempotent
    assert graph_stances.set_stance("acct:ada", "abolish", None, NOW) == {"approves": 0, "opposes": 0, "my_stance": None}
    assert stances(live_graph) == []


def test_withdrawal_also_removes_a_stance_a_post_made(live_graph):
    run(live_graph, SETUP)
    run(live_graph, "MATCH (p:Person {key: 'acct:ada'}), (s:Solution {key: 'abolish'}) "
                    "CREATE (p)-[:APPROVE {post_id: 'post-1', anonymous: false, created_at: $now}]->(s)")
    graph_stances.set_stance("acct:ada", "abolish", None, NOW)
    assert stances(live_graph) == []


def test_an_unknown_solution_or_person_changes_nothing(live_graph):
    run(live_graph, SETUP)
    assert graph_stances.set_stance("acct:ada", "nowhere", "approve", NOW) is None
    assert graph_stances.set_stance("acct:nobody", "abolish", "approve", NOW) is None
    assert graph_stances.set_stance("acct:ada", "nowhere", None, NOW) is None
    assert run(live_graph, "MATCH ()-[r:APPROVE|OPPOSE]->() RETURN count(r) AS n")[0]["n"] == 0


def test_concurrent_switches_leave_at_most_one_stance(live_graph):
    """Review Focus 1: approve and oppose pressed from two tabs at once, many times."""
    run(live_graph, SETUP)
    errors = []

    def press(choice):
        try:
            for _ in range(15):
                graph_stances.set_stance("acct:ada", "abolish", choice, NOW)
        except Exception as exc:  # noqa: BLE001  report any failure from a thread
            errors.append(exc)

    threads = [threading.Thread(target=press, args=(choice,)) for choice in ("approve", "oppose", None)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(stances(live_graph)) <= 1


def test_a_stance_waits_for_a_transaction_holding_the_person(live_graph):
    """Item 28 of the 5 October review: the test above can pass without the locks. Here another
    transaction holds the person and adds an approval it has not committed. Without the lock taken
    first, the click would not see that approval and both would remain; with it, the click waits,
    then replaces it."""
    run(live_graph, SETUP)
    session = live_graph.driver().session(database=live_graph.database())
    held = session.begin_transaction()
    held.run("MATCH (p:Person {key: 'acct:ada'}), (s:Solution {key: 'abolish'}) SET p.key = p.key "
             "CREATE (p)-[:APPROVE {post_id: 'held', anonymous: false, created_at: $now}]->(s)", now=NOW).consume()
    done = []
    thread = threading.Thread(target=lambda: done.append(graph_stances.set_stance("acct:ada", "abolish", "oppose", NOW)))
    thread.start()
    thread.join(timeout=1.0)
    try:
        assert thread.is_alive() and done == []  # waiting for the other transaction
    finally:
        held.commit()
        session.close()
    thread.join(timeout=15)
    assert done == [{"approves": 0, "opposes": 1, "my_stance": "OPPOSE"}]
    assert stances(live_graph) == [("OPPOSE", "click", None)]


def test_old_double_stances_count_both_ways_until_a_new_stance(live_graph):
    """Review Focus 2 (D7): a 0.1 person with both stances adds nothing net until they choose again."""
    run(live_graph, SETUP)
    run(live_graph, "MATCH (p:Person {key: 'name:grace'}), (s:Solution {key: 'abolish'}) "
                    "CREATE (p)-[:APPROVE {post_id: 'old-1', anonymous: false, created_at: $now}]->(s) "
                    "CREATE (p)-[:OPPOSE {post_id: 'old-2', anonymous: false, created_at: $now}]->(s)")
    assert graph_stances.set_stance("acct:ada", "abolish", "approve", NOW) == {"approves": 2, "opposes": 1, "my_stance": "APPROVE"}
    assert len(stances(live_graph, "name:grace")) == 2
    graph_stances.set_stance("name:grace", "abolish", "approve", NOW)
    assert [t for t, _, _ in stances(live_graph, "name:grace")] == ["APPROVE"]


def test_a_post_by_an_account_replaces_an_earlier_approval_and_a_passphrase_post_keeps_both(live_graph):
    from app.extract import ResolvedPayload
    run(live_graph, SETUP)
    graph_stances.set_stance("acct:ada", "abolish", "approve", NOW)
    payload = ResolvedPayload(solutions=[{"key": "abolish", "name": "Abolish the veto", "for_issue_key": "veto",
                                          "stance": "oppose", "stance_only": True}])
    live_graph.merge_post("acct:ada", "Ada", False, "Ada", "I now oppose abolishing the veto", payload, one_stance=True)
    assert [t for t, _, _ in stances(live_graph)] == ["OPPOSE"]
    # With accounts off a 0.1 person may still hold both, as today (X1).
    run(live_graph, "MATCH (p:Person {key: 'name:grace'}), (s:Solution {key: 'abolish'}) "
                    "CREATE (p)-[:APPROVE {post_id: 'old-1', anonymous: false, created_at: $now}]->(s)")
    live_graph.merge_post("name:grace", "Grace", False, "Grace", "I oppose it now", payload)
    assert sorted(t for t, _, _ in stances(live_graph, "name:grace")) == ["APPROVE", "OPPOSE"]
