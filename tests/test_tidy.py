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
    assert result.headers["location"] == "/issues/building%20a%20platform?done=renamed#tidy"
    result = client.post("/issues/platform/rename", data={"new_name": "World"}, follow_redirects=False)
    assert result.headers["location"] == "/issues/platform?problem=taken#tidy"
    assert "Another issue already has that name. To join the two, use Merge." in client.get("/issues/platform?problem=taken").text
    assert "Renamed." in client.get("/issues/platform?done=renamed").text
    result = client.post("/issues/platform/move", data={"parent": ""}, follow_redirects=False)
    assert result.headers["location"] == "/issues/platform?done=moved#tidy" and tidying.calls[-1] == ("move", "platform", None)


def test_merge_asks_first_then_says_what_happened(tidying):
    tidying.sign_in(admin=True)
    question = tidying.client.get("/issues/platform/merge?other=online%20platform").text
    assert ("Merge Online platform into Platform for digital democracy? Its claims, solutions, evidence and the issues "
            "that are part of it move here, and Online platform is removed. This cannot be undone. It is recorded in "
            "the list of changes.") in question.replace("\n", " ")
    result = tidying.client.post("/issues/platform/merge", data={"other": "online platform"}, follow_redirects=False)
    assert result.headers["location"] == "/issues/platform?done=merged&change=c1#tidy"
    assert "Merged. Everything about Online platform is now here." in tidying.client.get(result.headers["location"]).text
    assert tidying.client.get("/issues/platform/merge?other=platform", follow_redirects=False).headers["location"] == \
        "/issues/platform?problem=choose_other#tidy"


def test_the_list_of_changes(tidying, monkeypatch):
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


def test_reload_seed_writes_nothing_when_complete(monkeypatch):
    from scripts import seed
    data = {"issues": [{"name": "Platform for digital democracy"}],
            "posts": [{"id": "seed-01", "author": "John Kintree", "created_at": "2026-09-01T10:00:00Z", "text": "x",
                       "issues": [], "solutions": [], "evidence": []}]}
    monkeypatch.setattr(seed.graph, "existing_post_ids", lambda ids: set(ids))
    monkeypatch.setattr(seed.graph, "seed_issues", lambda *a, **kw: pytest.fail("no write when the seed is complete"))
    monkeypatch.setattr(seed.graph, "merge_post", lambda *a, **kw: pytest.fail("no write when the seed is complete"))
    assert seed.load(data) == (0, 1)


def test_tidied_names_follow_every_rename_and_merge_to_its_end():
    changes = [  # oldest first, as tidy_history() returns them
        row("rename", from_key="veto", from_name="veto", to_key="veto", to_name="Veto"),
        row("rename", from_key="parking", from_name="Parking", to_key="car parking", to_name="Car parking"),
        row("merge", merged_key="car parking", merged_name="Car parking", kept_key="transport", kept_name="Transport")]
    names = tidy.tidied_names(changes)
    assert names == {"parking": "Transport", "car parking": "Transport", "veto": "Veto"}
    assert tidy.retidy("Parking", names) == "Transport" and tidy.retidy("Housing", names) == "Housing"
    assert tidy.retidy(None, names) is None


def test_reload_seed_reads_a_renamed_seed_issue_as_it_is_now(monkeypatch):
    """Item 40: a seed post was deleted, and John had renamed a seed issue. Reload puts the post back
    on the issue under its new name; the old name does not come back, in the issues block or the post."""
    from scripts import seed
    from app.extract import Candidates
    old, new = "Platform for digital democracy", "Building a platform for digital democracy"
    data = {"issues": [{"name": old}, {"name": "Voting online", "parent": old}],
            "posts": [{"id": "seed-01", "author": "John Kintree", "created_at": "2026-09-01T10:00:00Z", "text": "x",
                       "issues": [], "solutions": [], "evidence": []},
                      {"id": "seed-02", "author": "John Kintree", "created_at": "2026-09-01T11:00:00Z", "text": "y",
                       "issues": [{"name": old}], "solutions": [], "evidence": []}]}
    monkeypatch.setattr(seed.graph, "existing_post_ids", lambda ids: {"seed-01"})
    monkeypatch.setattr(seed.graph_tidy, "tidy_history", lambda: [row(
        "rename", from_key="platform for digital democracy", from_name=old,
        to_key="building a platform for digital democracy", to_name=new)])
    written, posted = [], []
    monkeypatch.setattr(seed.graph, "seed_issues", lambda issues, created_at: written.extend(issues))
    monkeypatch.setattr(seed.graph, "candidates", lambda: Candidates(issues={
        "building a platform for digital democracy": {"name": new, "parent_key": None}}))
    monkeypatch.setattr(seed.graph, "merge_post", lambda *args, **kwargs: posted.append(args))
    assert seed.load(data) == (1, 1)
    assert [(item["name"], item.get("parent")) for item in written] == [(new, None), ("Voting online", new)]
    assert [issue["key"] for issue in posted[0][5].issues] == ["building a platform for digital democracy"]


def test_tidied_names_ignore_a_step_made_stale_when_a_key_is_used_again():
    merged_then_taken = [
        row("merge", merged_key="y", merged_name="Y", kept_key="z", kept_name="Z"),
        row("rename", from_key="x", from_name="X", to_key="y", to_name="Y")]
    assert tidy.tidied_names(merged_then_taken) == {"x": "Y"}
    back_again = [
        row("rename", from_key="a", from_name="A", to_key="b", to_name="B"),
        row("rename", from_key="b", from_name="B", to_key="a", to_name="A")]
    assert tidy.tidied_names(back_again) == {"b": "A"}


def test_moved_keys_follow_renames_and_merges():
    changes = [  # oldest first, as tidy_history() returns them
        row("move", issue_key="veto", issue_name="Veto", to_parent_key=None, to_parent_name=None),
        row("rename", from_key="veto", from_name="Veto", to_key="the veto", to_name="The veto"),
        row("move", issue_key="parking", issue_name="Parking", to_parent_key=None, to_parent_name=None),
        row("merge", merged_key="parking", merged_name="Parking", kept_key="transport", kept_name="Transport")]
    assert tidy.moved_keys(changes) == {"the veto", "transport"}  # a merge settles the kept issue too
    kept = [row("move", issue_key="law", issue_name="Law", to_parent_key=None, to_parent_name=None),
            row("merge", merged_key="world", merged_name="World", kept_key="law", kept_name="Law")]
    assert tidy.moved_keys(kept) == {"law"}


def test_reload_seed_keeps_a_moved_seed_issue_where_john_put_it(monkeypatch):
    """A move is tidying too: reload must not put a moved seed sub-issue back under its seed parent."""
    from scripts import seed
    from app.extract import Candidates
    top, sub = "Platform for digital democracy", "Voting online"
    data = {"issues": [{"name": top}, {"name": sub, "parent": top}],
            "posts": [{"id": "seed-01", "author": "John Kintree", "created_at": "2026-09-01T10:00:00Z", "text": "x",
                       "issues": [], "solutions": [], "evidence": []},
                      {"id": "seed-02", "author": "John Kintree", "created_at": "2026-09-01T11:00:00Z", "text": "y",
                       "issues": [{"name": sub, "parent": top}], "solutions": [], "evidence": []}]}
    monkeypatch.setattr(seed.graph, "existing_post_ids", lambda ids: {"seed-01"})
    monkeypatch.setattr(seed.graph_tidy, "tidy_history", lambda: [row(
        "move", issue_key="voting online", issue_name=sub, from_parent_key="platform for digital democracy",
        from_parent_name=top, to_parent_key=None, to_parent_name=None)])
    written, posted = [], []
    monkeypatch.setattr(seed.graph, "seed_issues", lambda issues, created_at: written.extend(issues))
    monkeypatch.setattr(seed.graph, "candidates", lambda: Candidates(issues={}))
    monkeypatch.setattr(seed.graph, "merge_post", lambda *args, **kwargs: posted.append(args))
    assert seed.load(data) == (1, 1)
    assert [(item["name"], item.get("parent")) for item in written] == [(top, None), (sub, None)]
    assert [(i["key"], i.get("parent_key")) for i in posted[0][5].issues] == [("voting online", None)]


def test_reload_seed_does_not_hang_a_merged_into_issue_under_the_old_seed_parent(monkeypatch):
    from scripts import seed
    from app.extract import Candidates
    data = {"issues": [{"name": "Platform"}, {"name": "Voting online", "parent": "Platform"}],
            "posts": [{"id": "seed-01", "author": "John Kintree", "created_at": "2026-09-01T10:00:00Z", "text": "x",
                       "issues": [], "solutions": [], "evidence": []},
                      {"id": "seed-02", "author": "John Kintree", "created_at": "2026-09-01T11:00:00Z", "text": "y",
                       "issues": [{"name": "Voting online", "parent": "Platform"}], "solutions": [], "evidence": []}]}
    monkeypatch.setattr(seed.graph, "existing_post_ids", lambda ids: {"seed-01"})
    monkeypatch.setattr(seed.graph_tidy, "tidy_history", lambda: [row(
        "merge", merged_key="voting online", merged_name="Voting online", kept_key="online voting", kept_name="Online voting")])
    written, posted = [], []
    monkeypatch.setattr(seed.graph, "seed_issues", lambda issues, created_at: written.extend(issues))
    monkeypatch.setattr(seed.graph, "candidates", lambda: Candidates(issues={}))
    monkeypatch.setattr(seed.graph, "merge_post", lambda *args, **kwargs: posted.append(args))
    assert seed.load(data) == (1, 1)
    assert [(i["name"], i.get("parent")) for i in written] == [("Platform", None), ("Online voting", None)]
    assert [(i["key"], i.get("parent_key")) for i in posted[0][5].issues] == [("online voting", None)]


def test_a_move_answering_same_goes_back_plain(tidying, monkeypatch):
    monkeypatch.setattr("app.graph_tidy.move_issue", lambda me, key, parent, now: "same")
    tidying.sign_in(admin=True)
    result = tidying.client.post("/issues/platform/move", data={"parent": ""}, follow_redirects=False)
    assert result.headers["location"] == "/issues/platform"


def test_a_move_answering_gone_goes_to_the_list(tidying, monkeypatch):
    monkeypatch.setattr("app.graph_tidy.move_issue", lambda me, key, parent, now: "gone")
    tidying.sign_in(admin=True)
    result = tidying.client.post("/issues/platform/move", data={"parent": ""}, follow_redirects=False)
    assert result.headers["location"] == "/issues"


def test_a_merge_that_found_nothing_asks_to_choose_again(tidying, monkeypatch):
    monkeypatch.setattr("app.graph_tidy.merge_issues", lambda me, kept, merged, now: ("gone", None))
    tidying.sign_in(admin=True)
    result = tidying.client.post("/issues/platform/merge", data={"other": "nothing"}, follow_redirects=False)
    assert result.headers["location"] == "/issues/platform?problem=choose_other#tidy"


def test_a_merge_into_a_missing_issue_goes_to_the_list(tidying, monkeypatch):
    monkeypatch.setattr("app.graph_tidy.merge_issues", lambda me, kept, merged, now: ("gone", None))
    monkeypatch.setattr(tidying.main.graph, "issue_header", lambda key: None)
    tidying.sign_in(admin=True)
    result = tidying.client.post("/issues/missing/merge", data={"other": "platform"}, follow_redirects=False)
    assert result.headers["location"] == "/issues"
