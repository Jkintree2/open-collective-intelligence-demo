"""group_issues on a hand made row list (Session 2, task 7) and the count line."""

from datetime import datetime, timezone

from app.graph import group_issues
from app.text import count_line


def _row(key, parent=None, people=None, claims=0, solutions=0, evidence=None, day=1):
    people = people or []
    evidence = evidence or []
    return {
        "key": key,
        "name": key.capitalize(),
        "seed": True,
        "parent_key": parent,
        "parent_name": parent.capitalize() if parent else None,
        "claims": claims,
        "people": len(people),
        "person_keys": people,
        "solutions": solutions,
        "evidence": len(evidence),
        "evidence_keys": evidence,
        "last_activity": datetime(2026, 9, day, tzinfo=timezone.utc),
    }


ROWS = [
    _row("world", people=["john"], claims=1, solutions=1, evidence=["udhr"], day=1),
    _row("veto", parent="world", people=["seed", "counter"], claims=2, solutions=1, evidence=["a", "b", "c", "d"], day=3),
    _row("law", parent="world", people=["john"], claims=3, solutions=2, evidence=["udhr", "earth"], day=4),
    _row("climate", parent="world", people=["john", "seed"], claims=3, solutions=1, evidence=["e", "f"], day=3),
    # a one line post from a friend, top level, one person
    _row("parking", people=["anon:1"], claims=1, solutions=0, evidence=[], day=5),
]


def test_parent_ranks_on_inclusive_counts_and_children_are_attached():
    grouped = group_issues(ROWS, "people")
    assert [g["key"] for g in grouped] == ["world", "parking"]
    world = grouped[0]
    assert world["people"] == 3            # john, seed, counter
    assert world["claims"] == 9            # 1 + 2 + 3 + 3
    assert world["own_claims"] == 1
    assert world["solutions"] == 5
    assert world["evidence"] == 8          # udhr shared between world and law counts once
    assert [c["key"] for c in world["children"]] == ["climate", "veto", "law"]


def test_most_recent_uses_the_newest_activity_in_the_family():
    grouped = group_issues(ROWS, "recent")
    assert [g["key"] for g in grouped] == ["parking", "world"]
    assert grouped[1]["last_activity"] == datetime(2026, 9, 4, tzinfo=timezone.utc)
    assert [c["key"] for c in grouped[1]["children"]] == ["law", "veto", "climate"]


def test_most_evidence_sorts_children_by_their_own_evidence():
    grouped = group_issues(ROWS, "evidence")
    assert [c["key"] for c in grouped[0]["children"]] == ["veto", "law", "climate"]


def test_an_unknown_sort_falls_back_to_people():
    assert [g["key"] for g in group_issues(ROWS, "sideways")] == ["world", "parking"]


def test_count_line_for_a_parent_and_for_a_leaf():
    parent = {"people": 3, "claims": 14, "own_claims": 1, "solutions": 9, "evidence": 14, "children": [1]}
    assert count_line(parent) == "3 people · 14 claims in total · 1 claim on the issue itself · 9 solutions · 14 pieces of evidence"
    leaf = {"people": 1, "claims": 1, "own_claims": 1, "solutions": 1, "evidence": 1, "children": []}
    assert count_line(leaf) == "1 person · 1 claim · 1 solution · 1 piece of evidence"
