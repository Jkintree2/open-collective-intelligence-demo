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


def test_solutions_rank_by_net_support_with_accounts_and_keep_todays_order_without(live_graph):
    """Net support orders the list; ties go to more approvals, then the name. Without accounts (X1)
    the 0.1 order stays: proposers, then approvals, then the oldest first."""
    run(live_graph, """
    CREATE (i:Issue {key: 'veto', name: 'Veto', seed: false})
    WITH i
    UNWIND range(0, 3) AS n
    WITH i, n, [['b', 'Bravo'], ['a', 'Alpha'], ['c', 'Charlie'], ['d', 'Delta']][n] AS pair
    CREATE (s:Solution {key: pair[0], name: pair[1], seed: false, created_at: $now + duration({minutes: n})})
    CREATE (i)-[:HAVE_PROPOSED {created_at: $now}]->(s)
    """)
    people = [f"acct:{n}" for n in range(5)]
    run(live_graph, "UNWIND $keys AS k CREATE (:Person {key: k, name: k, anonymous: false})", keys=people)
    for person in people[:3]:
        graph_stances.set_stance(person, "b", "approve", NOW)      # Bravo +3 -2 = +1, 3 approvals
    for person in people[3:]:
        graph_stances.set_stance(person, "b", "oppose", NOW)
    graph_stances.set_stance(people[0], "a", "approve", NOW)        # Alpha +2
    graph_stances.set_stance(people[1], "a", "approve", NOW)
    graph_stances.set_stance(people[0], "c", "approve", NOW)        # Charlie +1, 1 approval
    run(live_graph, "CREATE (p:Person {key: 'name:old', name: 'Old', anonymous: false}) WITH p "
                    "MATCH (s:Solution {key: 'd'}) CREATE (p)-[:APPROVE {created_at: $now}]->(s) "
                    "CREATE (p)-[:OPPOSE {created_at: $now}]->(s)")   # Delta 0, the 0.1 double stance
    rows = live_graph.issue_solutions("veto", me=people[0], ranked=True)
    assert [row["name"] for row in rows] == ["Alpha", "Bravo", "Charlie", "Delta"]
    assert [row["my_stance"] for row in rows] == ["APPROVE", "APPROVE", "APPROVE", None]
    assert (rows[3]["approves"], rows[3]["opposes"]) == (1, 1)
    assert all(row["my_stance"] is None for row in live_graph.issue_solutions("veto", ranked=True))
    assert [row["name"] for row in live_graph.issue_solutions("veto")] == ["Bravo", "Alpha", "Charlie", "Delta"]


def test_proposers_count_an_accounts_anonymous_proposals_apart(live_graph):
    """D2 (option a): an account proposing the same solution once by name and once anonymously
    counts twice; 0.1 people count as today (two named proposals, one with no flag, count once)."""
    run(live_graph, SETUP)
    run(live_graph, "MATCH (ada:Person {key: 'acct:ada'}), (grace:Person {key: 'name:grace'}), "
                    "(s:Solution {key: 'abolish'}) "
                    "CREATE (ada)-[:PROPOSE {post_id: 'a1', anonymous: false, created_at: $now}]->(s) "
                    "CREATE (ada)-[:PROPOSE {post_id: 'a2', anonymous: true, created_at: $now}]->(s) "
                    "CREATE (grace)-[:PROPOSE {post_id: 'g1', anonymous: false, created_at: $now}]->(s) "
                    "CREATE (grace)-[:PROPOSE {post_id: 'g2', created_at: $now}]->(s) "
                    "CREATE (:Person {key: 'anon:1', anonymous: true})-[:PROPOSE {post_id: 'n1', anonymous: true, "
                    "created_at: $now}]->(s)")
    for ranked in (False, True):
        assert live_graph.issue_solutions("veto", ranked=ranked)[0]["proposers"] == 4  # Ada twice, Grace, anon:1
