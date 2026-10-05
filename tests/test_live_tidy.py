import json
from datetime import datetime, timedelta, timezone

import pytest

from app import graph_tidy

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 9, 14, 2, tzinfo=timezone.utc)

TREE = """
CREATE (john:Person {key: 'acct:john', name: 'John Kintree', admin: true})
CREATE (world:Issue {key: 'world', name: 'World', seed: false, created_at: $now})
CREATE (veto:Issue {key: 'veto', name: 'Veto', seed: false, created_at: $now})
CREATE (law:Issue {key: 'law', name: 'Law', seed: false, created_at: $now})
CREATE (parking:Issue {key: 'parking', name: 'Parking', seed: false, created_at: $now})
CREATE (veto)-[:PART_OF {created_at: $now}]->(world)
CREATE (law)-[:PART_OF {created_at: $now}]->(world)
CREATE (ada:Person {key: 'acct:ada', name: 'Ada'})
CREATE (ada)-[:CLAIM {post_id: 'p1', anonymous: false, created_at: $now}]->(parking)
"""


def run(graph, query, **params):
    return graph.driver().execute_query(query, now=NOW, database_=graph.database(), **params).records


def parent(graph, key):
    rows = run(graph, "MATCH (:Issue {key: $k})-[:PART_OF]->(p:Issue) RETURN p.key AS p", k=key)
    return rows[0]["p"] if rows else None


def assert_one_level(graph):
    assert run(graph, "MATCH (a:Issue)-[:PART_OF]->(b:Issue) WHERE a = b OR (b)-[:PART_OF]->(:Issue) "
                      "RETURN a.key AS a") == []


def changes(graph):
    return [(row["kind"], json.loads(row["details"])) for row in graph_tidy.list_changes()]


def test_moves_follow_the_one_level_rule_and_are_recorded(live_graph):
    run(live_graph, TREE)
    assert graph_tidy.move_issue("acct:john", "world", "parking", NOW) == "has_children"  # World holds Veto and Law
    assert graph_tidy.move_issue("acct:john", "parking", "world", NOW) == "moved"
    assert parent(live_graph, "parking") == "world"
    assert graph_tidy.move_issue("acct:john", "parking", "world", NOW) == "same"
    assert graph_tidy.move_issue("acct:john", "parking", "veto", NOW) == "parent_is_sub"
    assert graph_tidy.move_issue("acct:john", "parking", "parking", NOW) == "self"
    assert graph_tidy.move_issue("acct:john", "nowhere", "world", NOW) == "gone"
    assert graph_tidy.move_issue("acct:john", "veto", None, NOW) == "moved"
    assert parent(live_graph, "veto") is None
    assert graph_tidy.move_issue("acct:john", "veto", None, NOW) == "same"
    assert_one_level(live_graph)
    kinds = changes(live_graph)
    assert [k for k, _ in kinds] == ["move", "move"]
    details = {d["issue_key"]: d for _, d in kinds}
    assert details["parking"]["to_parent_name"] == "World" and details["parking"]["from_parent_key"] is None
    assert details["veto"]["from_parent_name"] == "World" and details["veto"]["to_parent_key"] is None
    row = graph_tidy.list_changes()[0]
    assert row["by"] == "John Kintree" and row["issue_key"] in ("parking", "veto")


def test_rename_keeps_claims_and_refuses_a_taken_name(live_graph):
    run(live_graph, TREE)
    # Same key, new spelling: only the name changes. (clean_name() capitalises a lower-case first letter,
    # so "parking" would come back as "Parking", the same name.)
    assert graph_tidy.rename_issue("acct:john", "parking", "PARKING", NOW) == ("renamed", "parking")
    assert graph_tidy.rename_issue("acct:john", "parking", "PARKING", NOW) == ("same", "parking")
    assert graph_tidy.rename_issue("acct:john", "parking", "parking", NOW) == ("renamed", "parking")  # back to "Parking"
    assert graph_tidy.rename_issue("acct:john", "parking", "Car parking in town", NOW) == ("renamed", "car parking in town")
    assert run(live_graph, "MATCH (:Person)-[c:CLAIM]->(i:Issue {key: 'car parking in town'}) RETURN count(c) AS n")[0]["n"] == 1
    assert graph_tidy.rename_issue("acct:john", "car parking in town", "Law", NOW) == ("taken", "car parking in town")
    assert graph_tidy.rename_issue("acct:john", "car parking in town", "!!", NOW) == ("short", "car parking in town")
    assert graph_tidy.rename_issue("acct:john", "nowhere", "Anything", NOW) == ("gone", "nowhere")
    renames = [d for k, d in changes(live_graph) if k == "rename"]
    assert {(d["from_name"], d["to_name"]) for d in renames} == {
        ("Parking", "PARKING"), ("PARKING", "Parking"), ("Parking", "Car parking in town")}


def test_choices_offer_top_level_parents_and_every_other_issue(live_graph):
    run(live_graph, TREE)
    choices = graph_tidy.tidy_choices("parking")
    assert [c["key"] for c in choices["parents"]] == ["world"]  # Veto and Law are sub-issues
    assert sorted(c["key"] for c in choices["others"]) == ["law", "veto", "world"]
    assert graph_tidy.tidy_choices("world")["has_children"] is True


def double_submit(monkeypatch, call):
    """Run the same call a second time inside the first call's transaction, right after its
    first statement (the lock), as a double click would interleave."""
    real, state = graph_tidy._write, {"inner": None}

    def interleaved(work):
        def wrapped(tx):
            class Spy:
                def run(self, query, **params):
                    result = tx.run(query, **params)
                    if state["inner"] is None and query == graph_tidy.LOCK_ISSUES:
                        state["inner"] = work(tx)  # the second submit, on the locked state
                    return result
            return work(Spy())
        return real(wrapped)
    monkeypatch.setattr(graph_tidy, "_write", interleaved)
    outer = call()
    return state["inner"], outer


def test_a_double_submit_records_one_change(live_graph, monkeypatch):
    run(live_graph, TREE)
    inner, outer = double_submit(monkeypatch, lambda: graph_tidy.move_issue("acct:john", "parking", "world", NOW))
    assert (inner, outer) == ("moved", "same")
    inner, outer = double_submit(monkeypatch, lambda: graph_tidy.rename_issue("acct:john", "parking", "Car parking", NOW))
    assert (inner, outer) == (("renamed", "car parking"), ("same", "car parking"))
    assert sorted(k for k, _ in changes(live_graph)) == ["move", "rename"]


MERGE_SETUP = """
CREATE (john:Person {key: 'acct:john', name: 'John Kintree', admin: true})
CREATE (ada:Person {key: 'acct:ada', name: 'Ada'}), (bob:Person {key: 'name:bob', name: 'Bob'})
CREATE (a:Issue {key: 'platform', name: 'Platform for digital democracy', seed: true, created_at: $now})
CREATE (b:Issue {key: 'online platform', name: 'Online platform', seed: false, created_at: $now})
CREATE (c1:Issue {key: 'c1', name: 'C1', seed: false}), (c2:Issue {key: 'c2', name: 'C2', seed: false})
CREATE (c1)-[:PART_OF {created_at: $now}]->(b), (c2)-[:PART_OF {created_at: $now}]->(b)
CREATE (ada)-[:CLAIM {post_id: 'p1', anonymous: false, created_at: $now}]->(b)
CREATE (bob)-[:CLAIM {post_id: 'p2', anonymous: true, created_at: $now}]->(b)
CREATE (ada)-[:CLAIM {post_id: 'p3', anonymous: false, created_at: $now}]->(a)
CREATE (s1:Solution {key: 's1', name: 'S1'}), (s2:Solution {key: 's2', name: 'S2'})
CREATE (a)-[:HAVE_PROPOSED {post_id: 'pa', created_at: $now}]->(s1)
CREATE (b)-[:HAVE_PROPOSED {post_id: 'pb', created_at: $now}]->(s1)
CREATE (b)-[:HAVE_PROPOSED {post_id: 'pb2', created_at: $now}]->(s2)
CREATE (ada)-[:APPROVE {source: 'click', anonymous: false, created_at: $now}]->(s2)
CREATE (e1:Evidence {key: 'e1', name: 'E1'}), (e2:Evidence {key: 'e2', name: 'E2'})
CREATE (e1)-[:SUPPORTS {post_id: 'p4', created_at: $now}]->(b)
CREATE (e2)-[:REFUTES {post_id: 'p5', created_at: $now}]->(b)
CREATE (old:Change {id: 'old', kind: 'rename', created_at: $earlier, details: '{}'})
CREATE (john)-[:MADE {created_at: $earlier}]->(old)
CREATE (old)-[:CHANGED {created_at: $earlier}]->(b)
"""


def test_merge_moves_everything_and_records_it(live_graph):
    # The earlier change is a day older, so "newest first" puts the merge first (item 8 of the review).
    run(live_graph, MERGE_SETUP, earlier=NOW - timedelta(days=1))
    outcome, change_id = graph_tidy.merge_issues("acct:john", "platform", "online platform", NOW)
    assert outcome == "merged" and change_id
    assert run(live_graph, "MATCH (i:Issue {key: 'online platform'}) RETURN i") == []
    claims = run(live_graph, "MATCH (:Person)-[c:CLAIM]->(:Issue {key: 'platform'}) RETURN c.post_id AS p, c.anonymous AS a")
    assert sorted((r["p"], r["a"]) for r in claims) == [("p1", False), ("p2", True), ("p3", False)]
    proposed = run(live_graph, "MATCH (:Issue {key: 'platform'})-[h:HAVE_PROPOSED]->(s) RETURN s.key AS s, h.post_id AS p")
    assert sorted((r["s"], r["p"]) for r in proposed) == [("s1", "pa"), ("s2", "pb2")]
    solutions = {row["key"]: row for row in live_graph.issue_solutions("platform")}
    assert solutions["s2"]["approves"] == 1  # the stance followed its solution
    evidence = run(live_graph, "MATCH (e:Evidence)-[r]->(:Issue {key: 'platform'}) RETURN e.key AS e, type(r) AS t")
    assert sorted((r["e"], r["t"]) for r in evidence) == [("e1", "SUPPORTS"), ("e2", "REFUTES")]
    assert parent(live_graph, "c1") == "platform" and parent(live_graph, "c2") == "platform"
    history = run(live_graph, "MATCH (c:Change)-[:CHANGED]->(:Issue {key: 'platform'}) RETURN c.id AS id")
    assert sorted(r["id"] for r in history) == sorted(["old", change_id])
    kind, details = changes(live_graph)[0]
    assert kind == "merge" and details["kept_name"] == "Platform for digital democracy"
    assert details["merged_name"] == "Online platform"
    assert details["moved"] == {"CLAIM": 2, "SUPPORTS": 1, "REFUTES": 1, "HAVE_PROPOSED": 2, "PART_OF": 2, "CHANGED": 1}
    assert_one_level(live_graph)


@pytest.mark.parametrize("arrangement, expect", [
    # A is a sub-issue of P; B's sub-issue C goes under P, not under A.
    ("CREATE (p:Issue {key: 'p', name: 'P'}), (a:Issue {key: 'a', name: 'A'}), (b:Issue {key: 'b', name: 'B'}), "
     "(c:Issue {key: 'c', name: 'C'}) CREATE (a)-[:PART_OF {created_at: $now}]->(p), (c)-[:PART_OF {created_at: $now}]->(b)",
     {"a": "p", "c": "p"}),
    # A is a sub-issue of B; A becomes top level and B's other sub-issue D goes under A.
    ("CREATE (a:Issue {key: 'a', name: 'A'}), (b:Issue {key: 'b', name: 'B'}), (d:Issue {key: 'd', name: 'D'}) "
     "CREATE (a)-[:PART_OF {created_at: $now}]->(b), (d)-[:PART_OF {created_at: $now}]->(b)",
     {"a": None, "d": "a"}),
    # B is a sub-issue of A; no self-loop, A keeps its place.
    ("CREATE (a:Issue {key: 'a', name: 'A'}), (b:Issue {key: 'b', name: 'B'}) CREATE (b)-[:PART_OF {created_at: $now}]->(a)",
     {"a": None}),
    # B is a sub-issue of P and A is top level: A does not move.
    ("CREATE (p:Issue {key: 'p', name: 'P'}), (a:Issue {key: 'a', name: 'A'}), (b:Issue {key: 'b', name: 'B'}) "
     "CREATE (b)-[:PART_OF {created_at: $now}]->(p)",
     {"a": None}),
])
def test_merge_keeps_one_level_in_every_arrangement(live_graph, arrangement, expect):
    run(live_graph, "CREATE (:Person {key: 'acct:john', name: 'John Kintree', admin: true})")
    run(live_graph, arrangement)
    assert graph_tidy.merge_issues("acct:john", "a", "b", NOW)[0] == "merged"
    for key, expected_parent in expect.items():
        assert parent(live_graph, key) == expected_parent
    assert_one_level(live_graph)


def test_merging_an_issue_into_itself_or_a_missing_one(live_graph):
    run(live_graph, TREE)
    assert graph_tidy.merge_issues("acct:john", "world", "world", NOW) == ("self", None)
    assert graph_tidy.merge_issues("acct:john", "world", "nowhere", NOW) == ("gone", None)
    assert changes(live_graph) == []


def test_a_double_submitted_merge_records_one_change(live_graph, monkeypatch):
    run(live_graph, MERGE_SETUP, earlier=NOW - timedelta(days=1))
    inner, outer = double_submit(monkeypatch, lambda: graph_tidy.merge_issues("acct:john", "platform", "online platform", NOW))
    assert inner[0] == "merged" and outer == ("gone", None)
    assert [k for k, _ in changes(live_graph)].count("merge") == 1


def race_a_rename(live_graph, waiter):
    """A rename of issue 'a' commits while `waiter` (run in a second transaction) waits on its lock."""
    import threading
    run(live_graph, "CREATE (:Person {key: 'acct:john', name: 'John Kintree', admin: true}), "
                    "(:Issue {key: 'a', name: 'A'}), (:Issue {key: 'p', name: 'P'})")
    holding, release = threading.Event(), threading.Event()
    result = {}

    def renamer():
        def work(tx):
            tx.run(graph_tidy.LOCK_ISSUES, keys=["a"]).consume()
            tx.run(graph_tidy.RENAME, key="a", new_key="a two", new_name="A two").consume()
            holding.set()
            release.wait(5)
        graph_tidy._write(work)

    def waiting():
        result["value"] = waiter()

    t1 = threading.Thread(target=renamer)
    t2 = threading.Thread(target=waiting)
    try:
        t1.start()
        assert holding.wait(5)
        t2.start()
        t2.join(0.5)
        assert t2.is_alive()  # it is waiting on the lock of A: the two transactions overlap
    finally:
        release.set()
        t1.join(5)
        t2.join(5)
    assert not t1.is_alive() and not t2.is_alive()
    return result["value"]


def test_a_rename_committed_while_a_move_waits_is_not_undone(live_graph):
    move = race_a_rename(live_graph, lambda: graph_tidy.move_issue("acct:john", "a", "p", NOW))
    assert move == "gone"  # the key it was asked about no longer exists
    rows = run(live_graph, "MATCH (i:Issue) WHERE i.name STARTS WITH 'A' RETURN i.key AS k, i.name AS n")
    assert [(r["k"], r["n"]) for r in rows] == [("a two", "A two")]
    assert changes(live_graph) == []


def test_a_rename_committed_while_a_post_write_waits_is_not_undone(live_graph):
    from app import graph

    def post_write():
        def work(tx):
            tx.run(graph.MERGE_PART_OF, issue_key="a", parent_key="p", post_id="p9", now=NOW).consume()
        graph_tidy._write(work)

    race_a_rename(live_graph, post_write)
    rows = run(live_graph, "MATCH (i:Issue) WHERE i.name STARTS WITH 'A' RETURN i.key AS k, i.name AS n")
    assert [(r["k"], r["n"]) for r in rows] == [("a two", "A two")]
    assert run(live_graph, "MATCH (i:Issue {key: 'a'}) RETURN i") == []


def test_the_issues_list_counts_people_as_the_issue_page_does(live_graph):
    """D2 (option a): an account's anonymous claim counts apart from its named one, on the Issues list
    as on the issue page (Q3); 0.1 people count as today (a claim with no flag is named)."""
    run(live_graph, TREE)  # Ada's named claim on Parking (p1)
    run(live_graph, "MATCH (ada:Person {key: 'acct:ada'}), (i:Issue {key: 'parking'}) "
                    "CREATE (ada)-[:CLAIM {post_id: 'p2', anonymous: true, created_at: $now}]->(i) "
                    "CREATE (g:Person {key: 'name:grace', name: 'Grace'}) "
                    "CREATE (g)-[:CLAIM {post_id: 'p3', anonymous: false, created_at: $now}]->(i) "
                    "CREATE (g)-[:CLAIM {post_id: 'p4', created_at: $now}]->(i)")
    row = next(r for r in live_graph.list_issues() if r["key"] == "parking")
    assert (row["claims"], row["people"], len(row["person_keys"])) == (4, 3, 3)  # Ada, Ada anonymously, Grace
    assert live_graph.issue_claimants("parking")["people"] == row["people"]
    assert "Parking" in [item["name"] for item in live_graph.top_issues(5)]


def test_tidying_does_not_count_as_activity(live_graph):
    """A rename, and a move (item 18: Q28's PART_OF has a created_at), leave "Most recent" alone, for
    the issue and for its new parent."""
    run(live_graph, TREE)
    before = {row["key"]: row["last_activity"] for row in live_graph.list_issues()}
    later = datetime(2026, 12, 1, tzinfo=timezone.utc)
    graph_tidy.rename_issue("acct:john", "parking", "Car parking", later)
    assert graph_tidy.move_issue("acct:john", "car parking", "world", later) == "moved"
    after = {row["key"]: row["last_activity"] for row in live_graph.list_issues()}
    assert after["car parking"] == before["parking"]
    assert after["world"] == before["world"]


def test_reload_seed_after_a_move_keeps_the_issue_top_level(live_graph):
    """A seed post was deleted in the back room after John moved a seed sub-issue to the top level:
    reload puts the post back and leaves the issue where John put it."""
    from app import graph_backup
    from scripts import seed
    data = {"issues": [{"name": "Platform", "parent": None}, {"name": "Voting online", "parent": "Platform"}],
            "posts": [{"id": "seed-01", "author": "John Kintree", "created_at": "2026-09-01T10:00:00Z", "text": "x",
                       "issues": [{"name": "Platform", "parent": None}], "solutions": [], "evidence": []},
                      {"id": "seed-02", "author": "John Kintree", "created_at": "2026-09-01T11:00:00Z", "text": "y",
                       "issues": [{"name": "Voting online", "parent": "Platform"}], "solutions": [], "evidence": []}]}
    run(live_graph, "CREATE (:Person {key: 'acct:john', name: 'John Kintree', admin: true})")
    assert seed.load(data) == (2, 0)
    assert parent(live_graph, "voting online") == "platform"
    assert graph_tidy.move_issue("acct:john", "voting online", None, NOW) == "moved"
    assert graph_backup.delete_post("seed-02")
    assert seed.load(data) == (1, 1)
    assert run(live_graph, "MATCH (p:Post {id: 'seed-02'}) RETURN p.id AS id")
    assert parent(live_graph, "voting online") is None
    assert_one_level(live_graph)
