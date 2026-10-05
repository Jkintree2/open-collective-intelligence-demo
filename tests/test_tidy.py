import json
from datetime import datetime, timezone

import pytest

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
    rows = iter([None, place, {**place, "key": "world", "name": "World"}, None, {**place, "has_children": True}])

    class Tx:
        def run(self, query, **params):
            row = next(rows)
            return type("Result", (), {"single": lambda self: row, "consume": lambda self: None})()
    monkeypatch.setattr(graph_tidy, "_write", lambda work: work(Tx()))
    assert graph_tidy.move_issue("acct:john", "parking", "world", WHEN) == "has_children"

ISSUE = {"key": "platform", "name": "Platform for digital democracy", "parent_key": None, "parent_name": None,
         "children": [], "created_at": None, "seed": True}
# Each issue under its own name, so the merge question names both (item 9 of the 5 October review).
HEADERS = {"platform": ISSUE,
           "online platform": {**ISSUE, "key": "online platform", "name": "Online platform", "seed": False}}


@pytest.fixture
def tidying(member_app, monkeypatch):
    g = member_app.main.graph
    monkeypatch.setattr(g, "issue_header", lambda key: HEADERS.get(key))
    monkeypatch.setattr(g, "issue_claimants", lambda key: {"claims": 0, "people": 0, "names": []})
    monkeypatch.setattr(g, "issue_solutions", lambda key, me=None, ranked=False: [])  # C3's signature
    monkeypatch.setattr(g, "issue_evidence", lambda key: [])
    monkeypatch.setattr(g, "issue_posts", lambda key, limit: [])
    monkeypatch.setattr("app.graph_tidy.tidy_choices", lambda key: {
        "parents": [{"key": "world", "name": "World"}],
        "others": [{"key": "online platform", "name": "Online platform"}, {"key": "world", "name": "World"}],
        "has_children": False})
    calls = []
    monkeypatch.setattr("app.graph_tidy.rename_issue", lambda me, key, name, now: calls.append(("rename", key, name)) or
                        (("taken", key) if name == "World" else ("renamed", "building a platform")))
    monkeypatch.setattr("app.graph_tidy.move_issue", lambda me, key, parent, now: calls.append(("move", key, parent)) or "moved")
    monkeypatch.setattr("app.graph_tidy.merge_issues", lambda me, kept, merged, now: calls.append(("merge", kept, merged)) or ("merged", "c1"))
    monkeypatch.setattr("app.graph_tidy.change", lambda cid: {"kind": "merge", "details": '{"merged_name": "Online platform"}'} if cid == "c1" else None)
    monkeypatch.setattr("app.graph_tidy.list_changes", lambda: [])
    member_app.calls = calls
    return member_app


def test_john_sees_the_controls_and_others_do_not(tidying):
    tidying.sign_in(admin=True)
    page = tidying.client.get("/issues/platform").text
    assert "<h2>Tidy this issue</h2>" in page
    assert '<option value="">none, make it a top level issue</option>' in page
    assert '<option value="online platform">Online platform</option>' in page
    tidying.sign_in(key="acct:bob", name="Bob", email="bob@example.org", admin=False)
    assert "Tidy this issue" not in tidying.client.get("/issues/platform").text


def test_only_a_tidier_can_tidy(tidying):
    tidying.sign_in(admin=False)
    for path, data in (("/issues/platform/rename", {"new_name": "X marks"}), ("/issues/platform/move", {"parent": ""}),
                       ("/issues/platform/merge", {"other": "online platform"})):
        assert tidying.client.post(path, data=data).status_code == 404
    assert tidying.client.get("/issues/platform/merge?other=online%20platform").status_code == 404
    assert tidying.calls == []
    assert "Changes to the issues" in tidying.client.get("/changes").text  # every member reads the list


def test_tidy_answers_land_back_on_the_issue_page(tidying):
    tidying.sign_in(admin=True)
    client = tidying.client
    result = client.post("/issues/platform/rename", data={"new_name": "Building a platform"}, follow_redirects=False)
    assert result.headers["location"] == "/issues/building%20a%20platform?done=renamed"
    result = client.post("/issues/platform/rename", data={"new_name": "World"}, follow_redirects=False)
    assert result.headers["location"] == "/issues/platform?problem=taken"
    assert "Another issue already has that name. To join the two, use Merge." in client.get("/issues/platform?problem=taken").text
    assert "Renamed." in client.get("/issues/platform?done=renamed").text
    result = client.post("/issues/platform/move", data={"parent": ""}, follow_redirects=False)
    assert result.headers["location"] == "/issues/platform?done=moved" and tidying.calls[-1] == ("move", "platform", None)


def test_merge_asks_first_then_says_what_happened(tidying):
    tidying.sign_in(admin=True)
    question = tidying.client.get("/issues/platform/merge?other=online%20platform").text
    assert ("Merge Online platform into Platform for digital democracy? Its claims, solutions, evidence and the issues "
            "that are part of it move here, and Online platform is removed. This cannot be undone. It is recorded in "
            "the list of changes.") in question.replace("\n", " ")
    result = tidying.client.post("/issues/platform/merge", data={"other": "online platform"}, follow_redirects=False)
    assert result.headers["location"] == "/issues/platform?done=merged&change=c1"
    assert "Merged. Everything about Online platform is now here." in tidying.client.get(result.headers["location"]).text
    assert tidying.client.get("/issues/platform/merge?other=platform", follow_redirects=False).headers["location"] == \
        "/issues/platform?problem=choose_other"


def test_the_list_of_changes(tidying, monkeypatch):
    from datetime import datetime, timezone
    tidying.sign_in()
    page = tidying.client.get("/changes").text
    assert "Every move, rename and merge, newest first." in page and "No changes yet." in page
    monkeypatch.setattr("app.graph_tidy.list_changes", lambda: [
        {"kind": "rename", "created_at": datetime(2026, 10, 4, 14, 2, tzinfo=timezone.utc), "by": "John Kintree",
         "details": '{"from_name": "Platform for digital democracy", "to_name": "Building a platform for digital democracy"}'}])
    assert ("4 October 2026, 14:02 · John Kintree renamed Platform for digital democracy to Building a platform for "
            "digital democracy") in tidying.client.get("/changes").text
    assert '<a href="/changes">Changes to the issues</a>' in tidying.client.get("/issues").text


def test_a_repeated_rename_goes_back_to_the_key_it_answered(tidying, monkeypatch):
    monkeypatch.setattr("app.graph_tidy.rename_issue", lambda me, key, name, now: ("same", "new key"))
    tidying.sign_in(admin=True)
    result = tidying.client.post("/issues/platform/rename", data={"new_name": "New key"}, follow_redirects=False)
    assert result.headers["location"] == "/issues/new%20key"
