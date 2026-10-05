import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import graph_own_posts
from app.extract import CardPayload, Candidates, resolve_payload

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def card(graph, **fields):
    return resolve_payload(CardPayload.model_validate(fields), graph.candidates())


def post(graph, person, text, anonymous=False, **fields):
    name = None if anonymous else person.split(":")[1].capitalize()
    return graph.merge_post(person, name, anonymous, name, text, card(graph, **fields))


def rels(graph, post_id):
    return sorted(r["t"] for r in graph.driver().execute_query(
        "MATCH ()-[r]->() WHERE r.post_id = $id RETURN type(r) AS t", id=post_id, database_=graph.database()).records)


def test_edit_replaces_the_posts_own_edges_and_keeps_its_place(live_graph):
    pid = post(live_graph, "acct:ada", "Flooding needs seawalls", anonymous=True,
               issues=[{"name": "Flooding"}], solutions=[{"name": "Seawalls", "for_issue": "Flooding", "stance": "approve"}])
    before = live_graph.driver().execute_query("MATCH (p:Post {id: $id}) RETURN p.created_at AS c", id=pid,
                                               database_=live_graph.database()).records[0]["c"]
    assert rels(live_graph, pid) == ["APPROVE", "CLAIM", "HAVE_PROPOSED", "PROPOSE"]
    edited = card(live_graph, issues=[{"name": "Coastal flooding"}])
    assert graph_own_posts.edit_own_post("acct:ada", pid, edited, text="Coastal flooding matters", source="manual",
                                         extraction_raw=None, model=None, latency_ms=None, now=NOW + timedelta(hours=1))
    row = live_graph.driver().execute_query(
        "MATCH (:Person {key: 'acct:ada'})-[:POSTED]->(p:Post {id: $id}) RETURN p.text AS text, p.created_at AS c, "
        "p.edited_at AS e, p.anonymous AS anonymous", id=pid, database_=live_graph.database()).records[0]
    assert row["text"] == "Coastal flooding matters" and row["c"] == before and row["e"] is not None
    assert row["anonymous"] is True
    # Its own claim moved to the new issue; the shared link and the stance stay (MERGEd).
    assert rels(live_graph, pid) == ["APPROVE", "CLAIM", "HAVE_PROPOSED"]
    claim = live_graph.driver().execute_query("MATCH (:Person)-[r:CLAIM {post_id: $id}]->(i) RETURN i.name AS n, r.anonymous AS a",
                                              id=pid, database_=live_graph.database()).records[0]
    assert claim["n"] == "Coastal flooding" and claim["a"] is True


def test_edit_and_delete_remove_only_what_this_post_alone_made(live_graph):
    shared = post(live_graph, "acct:bob", "Flooding is real", issues=[{"name": "Flooding"}])
    mine = post(live_graph, "acct:ada", "Flooding and drought", issues=[{"name": "Flooding"}, {"name": "Drought"}])
    graph_own_posts.edit_own_post("acct:ada", mine, card(live_graph, issues=[{"name": "Heat"}]), text="Heat",
                                  source="manual", extraction_raw=None, model=None, latency_ms=None, now=NOW)
    names = lambda: sorted(r["n"] for r in live_graph.driver().execute_query(
        "MATCH (i:Issue) RETURN i.name AS n", database_=live_graph.database()).records)
    assert names() == ["Flooding", "Heat"]   # Drought was only this post's; Flooding is Bob's too
    assert graph_own_posts.delete_own_post("acct:ada", mine)
    assert names() == ["Flooding"]
    assert shared


def test_delete_keeps_approvals_and_what_they_hold(live_graph):
    """X2: a post that proposed and approved a new solution on a new issue. Delete takes its claim and
    its proposal; the approval stays (MERGEd), and so do the solution and the issue it hangs on."""
    pid = post(live_graph, "acct:ada", "Flooding needs seawalls", issues=[{"name": "Flooding"}],
               solutions=[{"name": "Seawalls", "for_issue": "Flooding", "stance": "approve"}])
    assert graph_own_posts.delete_own_post("acct:ada", pid)
    assert rels(live_graph, pid) == ["APPROVE", "HAVE_PROPOSED"]
    held = live_graph.driver().execute_query(
        "MATCH (:Person {key: 'acct:ada'})-[:APPROVE]->(s:Solution)<-[:HAVE_PROPOSED]-(i:Issue) "
        "RETURN s.name AS s, i.name AS i", database_=live_graph.database()).records
    assert [(r["s"], r["i"]) for r in held] == [("Seawalls", "Flooding")]
    assert live_graph.driver().execute_query("MATCH (p:Post {id: $id}) RETURN p", id=pid,
                                             database_=live_graph.database()).records == []


def test_two_deletes_at_once_remove_the_post_once(live_graph):
    """Item 34: the check locks the post, so the second delete waits and then finds it gone."""
    pid = post(live_graph, "acct:ada", "Mine", issues=[{"name": "Flooding"}])
    results, errors = [], []

    def delete():
        try:
            results.append(graph_own_posts.delete_own_post("acct:ada", pid))
        except Exception as exc:  # noqa: BLE001  report any failure from a thread
            errors.append(exc)
    threads = [threading.Thread(target=delete) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == [] and sorted(results) == [False, True]


def test_only_the_author_can_change_a_post(live_graph):
    pid = post(live_graph, "acct:ada", "Mine", issues=[{"name": "Flooding"}])
    live_graph.driver().execute_query("CREATE (:Person {key: 'name:seed'})-[:POSTED]->(:Post {id: 'seed-1', text: 's', seed: true})",
                                      database_=live_graph.database())
    edit = lambda who, which: graph_own_posts.edit_own_post(who, which, card(live_graph), text="x", source="manual",
                                                            extraction_raw=None, model=None, latency_ms=None, now=NOW)
    assert edit("acct:bob", pid) is False and graph_own_posts.delete_own_post("acct:bob", pid) is False
    assert edit("name:seed", "seed-1") is False and graph_own_posts.delete_own_post("name:seed", "seed-1") is False
    assert rels(live_graph, pid) == ["CLAIM"]
    assert graph_own_posts.post_owner("acct:bob", pid)["mine"] is False
    assert graph_own_posts.post_owner("acct:ada", pid)["mine"] is True
    assert graph_own_posts.post_owner("acct:ada", "nowhere") is None


def test_flags_say_mine_and_edited_without_naming_anyone(live_graph):
    a = post(live_graph, "acct:ada", "One", issues=[{"name": "Flooding"}])
    b = post(live_graph, "acct:bob", "Two", issues=[{"name": "Flooding"}])
    graph_own_posts.edit_own_post("acct:bob", b, card(live_graph, issues=[{"name": "Flooding"}]), text="Two again",
                                  source="manual", extraction_raw=None, model=None, latency_ms=None, now=NOW)
    flags = graph_own_posts.post_flags("acct:ada", [a, b])
    assert flags[a]["mine"] is True and flags[a]["edited_at"] is None
    assert flags[b]["mine"] is False and flags[b]["edited_at"] is not None
    assert set(flags[a]) == {"id", "edited_at", "mine"}
    assert all(not row["mine"] for row in graph_own_posts.post_flags(None, [a, b]).values())
