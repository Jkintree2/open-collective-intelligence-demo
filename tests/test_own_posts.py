import json as jsonlib
import re
from datetime import datetime, timezone

import pytest

from app import graph, graph_own_posts
from app.extract import CardPayload, Candidates, resolve_payload
from app.routes_own_posts import edit_card

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


class Result:
    def __init__(self, row):
        self.row = row

    def single(self):
        return self.row

    def consume(self):
        pass


def fake_driver(monkeypatch, *, owned, gone=False):
    calls, transactions, switches = [], [], []

    class Transaction:
        def run(self, query, **params):
            calls.append(query)
            if query == graph_own_posts.OWN_POST:
                return Result({"id": "p1", "anonymous": True} if owned else None)
            if query == graph.DELETE_POST:
                return Result(None if gone else {"touched": ["4:x:1"]})
            if query == graph_own_posts.DELETE_POST_EDGES:
                return Result(None if gone else {"touched": ["4:x:1"]})
            return Result(None)

    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute_write(self, work):
            transactions.append(True)
            return work(Transaction())

    monkeypatch.setattr(graph_own_posts, "driver", lambda: type("D", (), {"session": lambda self, **kw: Session()})())
    real = graph_own_posts.graph_posts.write_payload
    monkeypatch.setattr(graph_own_posts.graph_posts, "write_payload",
                        lambda tx, payload, common, **kw: switches.append(kw) or real(tx, payload, common, **kw))
    return calls, transactions, switches


def test_an_edit_is_one_transaction_in_the_agreed_order(monkeypatch):
    calls, transactions, switches = fake_driver(monkeypatch, owned=True)
    payload = resolve_payload(CardPayload.model_validate({"issues": [{"name": "Flooding"}]}), Candidates.empty())
    assert graph_own_posts.edit_own_post("acct:ada", "p1", payload, text="New", source="manual",
                                         extraction_raw=None, model=None, latency_ms=None, now=NOW) is True
    assert len(transactions) == 1
    assert calls[0] == graph_own_posts.OWN_POST and calls[1] == graph_own_posts.DELETE_POST_EDGES
    assert graph.MERGE_ISSUE_CLAIM in calls
    assert calls[-2:] == [graph.DELETE_POST_ORPHANS, graph_own_posts.UPDATE_POST]
    assert calls.index(graph.MERGE_ISSUE_CLAIM) < calls.index(graph.DELETE_POST_ORPHANS)
    assert switches == [{"one_stance": True}]  # an edit is always an account's (D7)


def test_the_check_locks_the_post():
    """Item 34 of the 5 October review: a second delete or edit waits for the first, then finds no post."""
    assert "SET post.id = post.id" in graph_own_posts.OWN_POST


def test_someone_elses_post_stops_after_the_check(monkeypatch):
    calls, _, _ = fake_driver(monkeypatch, owned=False)
    payload = resolve_payload(CardPayload(), Candidates.empty())
    assert graph_own_posts.edit_own_post("acct:bob", "p1", payload, text="x", source="manual",
                                         extraction_raw=None, model=None, latency_ms=None, now=NOW) is False
    assert graph_own_posts.delete_own_post("acct:bob", "p1") is False
    assert calls == [graph_own_posts.OWN_POST, graph_own_posts.OWN_POST]


def test_delete_is_the_check_then_q11(monkeypatch):
    calls, transactions, _ = fake_driver(monkeypatch, owned=True)
    assert graph_own_posts.delete_own_post("acct:ada", "p1") is True
    assert calls == [graph_own_posts.OWN_POST, graph.DELETE_POST, graph.DELETE_POST_ORPHANS]
    assert len(transactions) == 1


def test_a_post_gone_by_the_time_q11_runs_is_not_deleted_twice(monkeypatch):
    calls, _, _ = fake_driver(monkeypatch, owned=True, gone=True)
    assert graph_own_posts.delete_own_post("acct:ada", "p1") is False
    assert graph.DELETE_POST_ORPHANS not in calls


def test_flags_for_no_posts_ask_nothing(monkeypatch):
    monkeypatch.setattr(graph_own_posts, "_read", lambda *a, **kw: pytest.fail("no query for an empty page"))
    assert graph_own_posts.post_flags("acct:ada", []) == {}


def test_an_edit_on_a_post_gone_at_step_one_writes_nothing(monkeypatch):
    calls, _, switches = fake_driver(monkeypatch, owned=True, gone=True)
    payload = resolve_payload(CardPayload.model_validate({"issues": [{"name": "Flooding"}]}), Candidates.empty())
    assert graph_own_posts.edit_own_post("acct:ada", "p1", payload, text="New", source="manual",
                                         extraction_raw=None, model=None, latency_ms=None, now=NOW) is False
    assert calls == [graph_own_posts.OWN_POST, graph_own_posts.DELETE_POST_EDGES]
    assert switches == [] and graph_own_posts.UPDATE_POST not in calls


def test_own_posts_show_edit_and_delete_and_edited_shows_to_all(member_app, monkeypatch):
    now = datetime.now(timezone.utc)
    posts = [{"id": "mine-1", "text": "My statement", "display_name": None, "anonymous": True, "seed": False, "created_at": now},
             {"id": "theirs-1", "text": "Their statement", "display_name": "Bob", "anonymous": False, "seed": False, "created_at": now}]
    monkeypatch.setattr(member_app.main.graph, "list_posts", lambda limit: posts)
    monkeypatch.setattr("app.graph_own_posts.post_flags", lambda me, ids: {
        "mine-1": {"id": "mine-1", "edited_at": now, "mine": me == "acct:ada"},
        "theirs-1": {"id": "theirs-1", "edited_at": None, "mine": False}})
    member_app.sign_in()
    page = member_app.client.get("/").text
    assert page.count('href="/posts/mine-1/edit"') == 1 and page.count('href="/posts/mine-1/delete"') == 1
    assert "/posts/theirs-1/edit" not in page and "/posts/theirs-1/delete" not in page
    assert "· edited" in page
    assert "acct:ada" not in page
    member_app.sign_in(key="acct:bob", name="Bob", email="bob@example.org")
    other = member_app.client.get("/").text
    assert "/posts/mine-1/edit" not in other and "· edited" in other


def test_with_accounts_off_the_feed_asks_nothing_more(member_app, monkeypatch):
    """Item 38: no member, no flags query; the passphrase feed reads the record as today."""
    from dataclasses import replace
    off = replace(member_app.settings, accounts_enabled=False)
    for target in ("app.config.get_settings", "app.auth.get_settings"):
        monkeypatch.setattr(target, lambda: off)
    monkeypatch.setattr(member_app.main, "settings", off)
    monkeypatch.setattr(member_app.main.graph, "list_posts", lambda limit: [
        {"id": "one", "text": "Hello", "display_name": "Tester", "anonymous": False, "seed": False,
         "created_at": datetime.now(timezone.utc)}])
    monkeypatch.setattr("app.graph_own_posts.post_flags", lambda me, ids: pytest.fail("no flags without a member"))
    member_app.client.post("/enter", data={"passphrase": "gate words"})
    page = member_app.client.get("/").text
    assert "Hello" in page and "/posts/one/edit" not in page and "· edited" not in page


MINE_ROWS = [{"post_id": "mine-1", "rel": "CLAIM", "from_label": "Person", "from_key": "acct:ada", "from_name": "Ada",
              "to_label": "Issue", "to_key": "flooding", "to_name": "Flooding", "anonymous": False, "home_key": None}]


@pytest.fixture
def owned(member_app, monkeypatch):
    now = datetime.now(timezone.utc)
    record = {"mine-1": {"id": "mine-1", "text": "My statement", "anonymous": False, "created_at": now,
                         "payload": '{"issues": [{"key": "flooding", "name": "Flooding"}], "solutions": [], "evidence": []}'},
              "theirs-1": {"id": "theirs-1", "text": "Their statement", "anonymous": False, "created_at": now, "payload": "{}"}}
    owners = {"mine-1": "acct:ada", "theirs-1": "acct:bob"}
    monkeypatch.setattr("app.graph_own_posts.post_owner", lambda me, pid:
                        {**record[pid], "mine": owners[pid] == me} if pid in record else None)
    deleted = []
    monkeypatch.setattr("app.graph_own_posts.delete_own_post", lambda me, pid:
                        (owners.get(pid) == me and record.pop(pid, None) is not None and not deleted.append(pid)))
    monkeypatch.setattr("app.graph_own_posts.post_flags", lambda me, ids: {})
    # The edit card reads the post's edges as they are now (Q7's structure query) and the issue's header.
    g = member_app.main.graph
    monkeypatch.setattr(g, "post_structure", lambda ids: {"mine-1": MINE_ROWS} if ids == ["mine-1"] else {})
    monkeypatch.setattr(g, "issue_header", lambda key: {"key": "flooding", "name": "Flooding", "parent_key": None,
                                                         "parent_name": None, "children": []} if key == "flooding" else None)
    member_app.sign_in()
    member_app.record, member_app.deleted = record, deleted
    return member_app


def test_delete_asks_first_then_removes_and_says_so(owned):
    question = owned.client.get("/posts/mine-1/delete").text
    assert ("Delete this post? What it claimed, proposed and cited goes, unless something else still uses it. "
            "Approvals and oppositions stay; you can change them on the issue page.") in question
    assert "My statement" in question and "Keep it" in question
    result = owned.client.post("/posts/mine-1/delete", follow_redirects=False)
    assert result.status_code == 303 and result.headers["location"] == "/?done=deleted"
    assert owned.deleted == ["mine-1"]
    assert "Your post is deleted." in owned.client.get("/?done=deleted").text


def test_deleting_someone_elses_post_is_refused(owned):
    for method in ("get", "post"):
        result = getattr(owned.client, method)("/posts/theirs-1/delete")
        assert result.status_code == 403 and "You can change only your own posts." in result.text
    assert owned.deleted == []


def test_a_post_gone_meanwhile_says_so(owned):
    for method in ("get", "post"):
        result = getattr(owned.client, method)("/posts/nowhere/delete")
        assert result.status_code == 404 and "That post is no longer here." in result.text


def test_delete_needs_an_account_and_this_site(owned, monkeypatch):
    refused = owned.client.post("/posts/mine-1/delete", headers={"Origin": "https://other.example"})
    assert refused.status_code == 403 and "Please reload the page and try again." in refused.text
    from dataclasses import replace
    monkeypatch.setattr("app.config.get_settings", lambda: replace(owned.settings, accounts_enabled=False))
    assert owned.client.get("/posts/mine-1/delete").status_code == 404
    assert owned.deleted == []

def edge(rel, from_label, from_key, from_name, to_label, to_key, to_name, home_key=None):
    return {"post_id": "p1", "rel": rel, "from_label": from_label, "from_key": from_key, "from_name": from_name,
            "to_label": to_label, "to_key": to_key, "to_name": to_name, "anonymous": False, "home_key": home_key}


def test_the_edit_card_comes_from_the_posts_edges_as_they_are_now():
    """The issue was renamed since the post (its stored payload still says Flooding)."""
    rows = [
        edge("CLAIM", "Person", "acct:ada", "Ada", "Issue", "coastal flooding", "Coastal flooding"),
        edge("PROPOSE", "Person", "acct:ada", "Ada", "Solution", "seawalls", "Seawalls", "coastal flooding"),
        edge("HAVE_PROPOSED", "Issue", "coastal flooding", "Coastal flooding", "Solution", "seawalls", "Seawalls",
             "coastal flooding"),
        edge("APPROVE", "Person", "acct:ada", "Ada", "Solution", "seawalls", "Seawalls", "coastal flooding"),
        edge("SUBMIT", "Person", "acct:ada", "Ada", "Evidence", "report", "Report"),
        edge("REFUTES", "Evidence", "report", "Report", "Solution", "seawalls", "Seawalls", "coastal flooding"),
    ]
    stored = jsonlib.dumps({
        "issues": [{"key": "flooding", "name": "Flooding", "parent_key": None}],
        "solutions": [{"key": "seawalls", "name": "Seawalls", "for_issue_key": "flooding", "stance": "approve"}],
        "evidence": [{"key": "report", "name": "Report", "url": "https://example.org", "stance": "refutes",
                      "target_key": "seawalls", "target_label": "Solution"}]})
    issues = {"coastal flooding": {"name": "Coastal flooding", "parent_name": "World"}}
    assert edit_card(rows, stored, issues) == {
        "issues": [{"name": "Coastal flooding", "parent": "World"}],
        "solutions": [{"name": "Seawalls", "for_issue": "Coastal flooding", "stance": "approve"}],
        "evidence": [{"name": "Report", "url": "https://example.org", "stance": "refutes", "about": "Seawalls"}]}
    # A stance a click has since replaced is no longer this post's: no position, so saving changes nothing.
    clicked = [row for row in rows if row["rel"] != "APPROVE"]
    assert edit_card(clicked, stored, issues)["solutions"][0]["stance"] == "none"
    assert edit_card([], None, {}) == {"issues": [], "solutions": [], "evidence": []}


def test_the_edit_page_carries_the_post_and_its_card(owned, monkeypatch):
    monkeypatch.setattr(owned.main.graph, "candidates", Candidates.empty)
    page = owned.client.get("/posts/mine-1/edit")
    assert page.status_code == 200
    embedded = re.search(r'<script id="edit-post" type="application/json">(.*?)</script>', page.text, re.S).group(1)
    post = jsonlib.loads(embedded)
    assert post == {"id": "mine-1", "text": "My statement", "anonymous": False,
                    "card": {"issues": [{"name": "Flooding", "parent": None}], "solutions": [], "evidence": []}}
    assert "/static/edit_post.js?v=" in page.text
    # Without JavaScript the same form saves the edit; it never posts to /posts.
    assert 'action="/posts/mine-1/edit"' in page.text and 'action="/posts"' not in page.text
    assert ">Save changes</button>" in page.text
    home = owned.client.get("/").text
    assert home.count("edit_post.js") == 0 and 'action="/posts"' in home


def test_editing_someone_elses_post_is_refused_on_the_page(owned):
    result = owned.client.get("/posts/theirs-1/edit")
    assert result.status_code == 403 and "You can change only your own posts." in result.text


@pytest.fixture
def saving(owned, monkeypatch):
    monkeypatch.setattr(owned.main.graph, "candidates", Candidates.empty)
    saved = []
    monkeypatch.setattr("app.graph_own_posts.edit_own_post", lambda me, pid, payload, **kw:
                        pid in owned.record and not saved.append((me, pid, payload, kw)))
    owned.saved = saved
    return owned


def test_saving_an_edit_keeps_the_name_and_replaces_the_card(saving):
    result = saving.client.post("/api/posts/mine-1", json={"text": "Coastal flooding matters", "anonymous": True,
                                                          "issues": [{"name": "Coastal flooding"}]})
    assert result.status_code == 200 and result.json() == {"id": "mine-1", "message": "Your post is updated."}
    me, pid, payload, kw = saving.saved[0]
    assert (me, pid) == ("acct:ada", "mine-1")
    assert [issue["name"] for issue in payload.issues] == ["Coastal flooding"]
    assert kw["text"] == "Coastal flooding matters" and kw["source"] == "manual"
    assert "Your post is updated." in saving.client.get("/?done=edited").text


def test_saving_without_javascript_keeps_the_card_and_never_posts_anew(saving):
    """Item 7: the write form, pointed at this post, saves the new text with the post's current card."""
    result = saving.client.post("/posts/mine-1/edit", data={"text": "My statement, typo fixed"}, follow_redirects=False)
    assert result.status_code == 303 and result.headers["location"] == "/?done=edited"
    me, pid, payload, kw = saving.saved[0]
    assert (me, pid) == ("acct:ada", "mine-1") and [issue["name"] for issue in payload.issues] == ["Flooding"]
    assert kw["text"] == "My statement, typo fixed" and kw["source"] == "manual"
    assert saving.writes == []  # merge_post never ran: no new post
    refused = saving.client.post("/posts/theirs-1/edit", data={"text": "Hijack"})
    assert refused.status_code == 403 and len(saving.saved) == 1


def test_saving_someone_elses_post_is_refused(saving):
    result = saving.client.post("/api/posts/theirs-1", json={"text": "Hijack", "issues": [{"name": "X marks"}]})
    assert result.status_code == 403 and result.json() == {"message": "You can change only your own posts."}
    assert saving.saved == []


def test_saving_a_post_gone_meanwhile_says_so(saving):
    result = saving.client.post("/api/posts/nowhere", json={"text": "Hello", "issues": [{"name": "Flooding"}]})
    assert result.status_code == 404 and result.json() == {"message": "That post is no longer here."}
    assert saving.client.post("/posts/nowhere/edit", data={"text": "Hello"}).status_code == 404


def test_an_unusable_edit_is_refused_like_a_post(saving):
    assert saving.client.post("/api/posts/mine-1", json={"text": "x" * 4001}).status_code == 413
    assert saving.client.post("/api/posts/mine-1", json={"text": "Hello"}).status_code == 422
    assert saving.client.post("/api/posts/mine-1", json={"issues": "not a list", "text": 5}).status_code == 422
    assert saving.client.post("/posts/mine-1/edit", data={"text": "x" * 4001}).status_code == 413
    assert saving.saved == []


def test_write_page_renders_as_before_when_not_editing(member_app, monkeypatch):
    monkeypatch.setattr(member_app.main.graph, "list_posts", lambda limit: [])
    member_app.sign_in()
    page = member_app.client.get("/").text
    assert re.search(r'about_issue\.js\?v=[^"]*" defer></script>\n\n<section class="feed" id="feed">', page)
