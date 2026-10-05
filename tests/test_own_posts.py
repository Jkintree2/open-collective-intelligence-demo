from datetime import datetime, timezone

import pytest

from app import graph, graph_own_posts
from app.extract import CardPayload, Candidates, resolve_payload

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
                return Result({"touched": ["4:x:1"]})
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
