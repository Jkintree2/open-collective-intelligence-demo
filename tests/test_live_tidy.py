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
