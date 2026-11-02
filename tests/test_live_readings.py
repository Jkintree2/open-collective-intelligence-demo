"""Post.reading_payload and Q55, the back room's readings changed by their writers. Live: the disposable test
Neo4j only."""

import json
from datetime import datetime, timezone

import pytest

from app import graph_own_posts, graph_readings, readings
from app.extract import CardPayload, resolve_payload

pytestmark = pytest.mark.live
NOW = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)
FIELDS = {"id", "text", "display_name", "created_at", "edited_at", "payload", "extraction_raw", "reading_payload"}


def card(graph, **fields):
    return resolve_payload(CardPayload.model_validate({"found": True, **fields}), graph.candidates())


def post(graph, text, anonymous=False, person="acct:ada", **kwargs):
    name = "Ada"
    return graph.merge_post(person, name, anonymous, name, text, card(graph, issues=[{"name": "Heat waves"}]),
                            **kwargs)


def test_a_post_keeps_its_reading_and_the_page_lists_what_its_writer_changed(live_graph):
    reading = card(live_graph, issues=[{"name": "Heat"}]).as_json()
    post_id = post(live_graph, "Heat waves are a problem.", source="model", extraction_raw="{}",
                   reading_payload=reading)
    rows = graph_readings.posts_with_readings()
    assert [row["id"] for row in rows] == [post_id] and set(rows[0]) == FIELDS
    assert rows[0]["reading_payload"] == reading and rows[0]["display_name"] == "Ada"
    [shown], unreadable = readings.page_rows(rows, live_graph.candidates())
    assert (shown["taken_out"], shown["added"], unreadable) == (["claims Heat"], ["claims Heat waves"], 0)


def test_a_manual_post_and_a_reading_kept_as_it_was_are_not_listed(live_graph):
    post(live_graph, "Heat waves.")
    same = post(live_graph, "Heat waves again.", person="acct:bob", source="model", extraction_raw="{}",
                reading_payload=card(live_graph, issues=[{"name": "Heat waves"}]).as_json())
    rows = graph_readings.posts_with_readings()
    assert [row["id"] for row in rows] == [same]
    assert readings.page_rows(rows, live_graph.candidates()) == ([], 0)


def test_an_anonymous_post_is_listed_without_a_name(live_graph):
    post(live_graph, "Heat waves.", anonymous=True, source="model", extraction_raw="{}",
         reading_payload=card(live_graph).as_json())
    [row] = graph_readings.posts_with_readings()
    assert row["display_name"] is None and "Ada" not in json.dumps(row, default=str)
    assert readings.page_rows([row], live_graph.candidates())[0][0]["name"] == "Anonymous"


def test_an_edit_replaces_the_reading_or_clears_it(live_graph):
    post_id = post(live_graph, "Heat waves.", source="model", extraction_raw="{}",
                   reading_payload=card(live_graph).as_json())
    edited = card(live_graph, issues=[{"name": "Heat"}])
    edit = lambda **reading: graph_own_posts.edit_own_post("acct:ada", post_id, edited, text="Heat.", source="model",
                                                          model=None, latency_ms=None, now=NOW, **reading)
    assert edit(extraction_raw="{}", reading_payload=edited.as_json())
    assert graph_readings.posts_with_readings()[0]["reading_payload"] == edited.as_json()
    assert edit(extraction_raw=None)
    assert graph_readings.posts_with_readings() == []
    stored = live_graph.driver().execute_query("MATCH (p:Post {id: $id}) RETURN p.reading_payload AS kept",
                                               {"id": post_id}, database_=live_graph.database()).records
    assert stored[0]["kept"] is None


def test_a_copy_keeps_the_reading(live_graph):
    reading = card(live_graph).as_json()
    post_id = post(live_graph, "Heat waves.", source="model", extraction_raw="{}", reading_payload=reading)
    exported = json.loads(json.dumps(live_graph.export_record()))
    live_graph.driver().execute_query("MATCH (n) DETACH DELETE n", database_=live_graph.database())
    live_graph.restore_record(exported)
    assert graph_readings.posts_with_readings()[0]["reading_payload"] == reading
    assert graph_readings.posts_with_readings()[0]["id"] == post_id
