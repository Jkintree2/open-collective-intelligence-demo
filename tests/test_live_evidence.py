"""Phase 2 on the disposable Neo4j: a kept reading on the post's edge, source facts set once, nothing with
the flag off, an edit that keeps or drops a reading, and an export that restores with all of it."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import check, graph_evidence, graph_own_posts
from app.backup import validate_record
from app.check import Check, kept_checks
from app.extract import CardPayload, resolve_payload

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
URL = "https://news.example.org/story"
QUOTE = "A survey of forty coastal towns found flooding days doubled since 2000."
NEWS = {"type": "news", "primary": False, "published": "2024-03"}


@pytest.fixture(autouse=True)
def empty_cache():
    check.cache.clear()
    yield
    check.cache.clear()


def card(**row):
    evidence = {"name": "Forty town survey", "url": URL, "stance": "supports", "about": "Coastal flooding",
                "check": {"verdict": "supports", "quote": QUOTE}, **row}
    return CardPayload.model_validate({"issues": [{"name": "Coastal flooding"}], "evidence": [evidence]})


def read(verdict="supports", quote=QUOTE, source=NEWS, statement="Floods are worse."):
    check.cache.put(check.cache_key(URL, "Coastal flooding", statement),
                    Check(verdict, URL, quote=quote, source=source, checked_at=NOW.isoformat()))


def post(graph, person, sent, *, flag=True, statement="Floods are worse."):
    payload = resolve_payload(sent, graph.candidates())
    checks = kept_checks(sent.evidence, payload.evidence, statement) if flag else None
    return graph.merge_post(person, person.split(":")[1].capitalize(), False, None, statement, payload,
                            checks=checks), payload


def edge(graph, post_id):
    rows = graph.driver().execute_query(
        "MATCH (:Evidence)-[r:SUPPORTS|REFUTES]->() WHERE r.post_id = $id RETURN properties(r) AS p",
        id=post_id, database_=graph.database()).records
    return rows[0]["p"]


def evidence(graph):
    return graph.driver().execute_query("MATCH (e:Evidence {key: 'forty town survey'}) RETURN properties(e) AS p",
                                        database_=graph.database()).records[0]["p"]


def test_a_kept_reading_goes_on_the_edge_and_the_source_facts_on_the_evidence(live_graph):
    read()
    post_id, _ = post(live_graph, "acct:ada", card())
    props = edge(live_graph, post_id)
    assert props["check"] == "supports" and props["check_quote"] == QUOTE
    assert props["checked_at"].to_native() == NOW
    facts = evidence(live_graph)
    assert (facts["source_type"], facts["source_primary"], facts["source_published"]) == ("news", False, "2024-03")
    assert facts["source_checked_at"] is not None


def test_source_facts_are_set_once_and_never_overwritten(live_graph):
    read()
    post(live_graph, "acct:ada", card())
    first = evidence(live_graph)
    check.cache.clear()
    read(verdict="refutes", source={"type": "blog", "primary": True, "published": "2020"})
    later, _ = post(live_graph, "acct:bob", card(stance="refutes", check={"verdict": "refutes", "quote": QUOTE}))
    assert edge(live_graph, later)["check"] == "refutes"  # each post keeps its own reading
    assert evidence(live_graph) == first


def test_a_reading_the_site_never_made_is_stored_as_nothing(live_graph):
    post_id, _ = post(live_graph, "acct:ada", card())
    props = edge(live_graph, post_id)
    assert "check" not in props and "check_quote" not in props and "checked_at" not in props
    assert "source_type" not in evidence(live_graph)


def test_with_the_flag_off_nothing_new_is_written(live_graph):
    read()
    post_id, _ = post(live_graph, "acct:ada", card(), flag=False)
    assert set(edge(live_graph, post_id)) == {"post_id", "created_at"}
    assert not any(key.startswith("source_") for key in evidence(live_graph))


def test_an_edit_keeps_the_reading_the_post_holds_and_drops_one_for_a_new_link(live_graph):
    read()
    post_id, _ = post(live_graph, "acct:ada", card())
    check.cache.clear()  # a restart since: only the record remembers the reading
    stored = {key: {**row, "url": URL} for key, row in graph_evidence.post_checks(post_id).items()}
    assert stored[("forty town survey", "coastal flooding")]["check"] == "supports"
    sent = card()
    payload = resolve_payload(sent, live_graph.candidates())
    assert graph_own_posts.edit_own_post("acct:ada", post_id, payload, text="Floods are much worse.", source="manual",
                                         extraction_raw=None, model=None, latency_ms=None, now=NOW + timedelta(hours=1),
                                         checks=kept_checks(sent.evidence, payload.evidence, "Floods are much worse.", stored))
    props = edge(live_graph, post_id)
    assert props["check"] == "supports" and props["checked_at"].to_native() == NOW
    moved = card(url="https://other.example.org/")
    payload = resolve_payload(moved, live_graph.candidates())
    assert graph_own_posts.edit_own_post("acct:ada", post_id, payload, text="Floods are much worse.", source="manual",
                                         extraction_raw=None, model=None, latency_ms=None, now=NOW + timedelta(hours=2),
                                         checks=kept_checks(moved.evidence, payload.evidence, "x", stored))
    assert "check" not in edge(live_graph, post_id)


def test_export_then_restore_keeps_readings_and_source_facts(live_graph):
    read()
    post_id, _ = post(live_graph, "acct:ada", card())
    before_edge, before_evidence = edge(live_graph, post_id), evidence(live_graph)
    exported = json.loads(json.dumps(live_graph.export_record()))
    validate_record(exported)
    live_graph.driver().execute_query("MATCH (n) DETACH DELETE n", database_=live_graph.database())
    live_graph.restore_record(exported)
    assert edge(live_graph, post_id) == before_edge
    assert evidence(live_graph) == before_evidence
