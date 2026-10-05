import json
from datetime import datetime, timezone

from app import tidy
from app.members import Member

WHEN = datetime(2026, 10, 4, 14, 2, tzinfo=timezone.utc)


def row(kind, **details):
    return {"kind": kind, "created_at": WHEN, "details": json.dumps(details), "by": "John Kintree"}


def test_only_an_admin_account_tidies():
    assert tidy.can_tidy(Member("acct:john", "John Kintree", "j@example.org", True))
    assert not tidy.can_tidy(Member("acct:ada", "Ada", "a@example.org", False))
    assert not tidy.can_tidy(None)


def test_change_sentences_word_for_word():
    assert tidy.sentence(row("rename", from_name="Platform for digital democracy",
                             to_name="Building a platform for digital democracy")) == \
        "4 October 2026, 14:02 · John Kintree renamed Platform for digital democracy to Building a platform for digital democracy"
    assert tidy.sentence(row("move", issue_name="Veto", to_parent_name="World")) == \
        "4 October 2026, 14:02 · John Kintree moved Veto under World"
    assert tidy.sentence(row("move", issue_name="Veto", to_parent_name=None)) == \
        "4 October 2026, 14:02 · John Kintree made Veto a top level issue"
    assert tidy.sentence(row("merge", merged_name="Parking", kept_name="Car parking")) == \
        "4 October 2026, 14:02 · John Kintree merged Parking into Car parking"


def test_a_move_refused_after_the_lock_says_why(monkeypatch):
    """Item 37: Parking gained a sub-issue between the read and the lock. The move is refused because
    other issues are now part of it, and the answer says that, not that the parent is a sub-issue."""
    from app import graph_tidy
    place = {"key": "parking", "name": "Parking", "parent_key": None, "parent_name": None, "has_children": False}
    rows = iter([place, {**place, "key": "world", "name": "World"}, None, {**place, "has_children": True}])

    class Tx:
        def run(self, query, **params):
            row = next(rows)
            return type("Result", (), {"single": lambda self: row, "consume": lambda self: None})()
    monkeypatch.setattr(graph_tidy, "_write", lambda work: work(Tx()))
    assert graph_tidy.move_issue("acct:john", "parking", "world", WHEN) == "has_children"
