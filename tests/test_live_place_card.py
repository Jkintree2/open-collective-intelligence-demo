"""Phase 3, W3b on the disposable Neo4j: a post's place written by posting, read by Q24 for the edit card,
changed or kept by an edit, and carried by export and restore (03_schema.md, "A place on each post")."""

import json
from datetime import datetime, timezone

import pytest

from app import graph_own_posts
from app.backup import validate_record
from app.extract import CardPayload, resolve_payload
from app.payload import PlaceItem, resolve_place

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
PROPS = "p.place_country AS country, p.place_area AS area, p.place_area_key AS area_key"


def card(graph, **fields):
    return resolve_payload(CardPayload.model_validate(fields), graph.candidates())


def place_of(graph, post_id):
    rows = graph.driver().execute_query(f"MATCH (p:Post {{id: $id}}) RETURN {PROPS}, keys(p) AS keys",
                                        id=post_id, database_=graph.database()).records
    return rows[0].data()


def post(graph, place=None, text="The river floods every spring."):
    return graph.merge_post("acct:ada", "Ada", False, "Ada", text, card(graph, issues=[{"name": "River flooding"}]),
                            place=place)


def edit(post_id, graph, place):
    return graph_own_posts.edit_own_post("acct:ada", post_id, card(graph, issues=[{"name": "River flooding"}]),
                                         text="Edited", source="manual", extraction_raw=None, model=None,
                                         latency_ms=None, now=NOW, place=place)


def test_a_post_holds_its_place_and_one_without_holds_none(live_graph):
    placed = post(live_graph, resolve_place(PlaceItem(country="US", area="St. Louis")))
    assert place_of(live_graph, placed) | {"keys": None} == {"country": "US", "area": "St. Louis",
                                                             "area_key": "st louis", "keys": None}
    # No place (the switch unset, "Not about one place", seed posts) is absent from the post, not stored as null.
    for place in (None, resolve_place(PlaceItem())):
        other = post(live_graph, place)
        assert not {"place_country", "place_area", "place_area_key"} & set(place_of(live_graph, other)["keys"])


def test_the_edit_card_reads_the_place_and_an_edit_changes_or_keeps_it(live_graph):
    pid = post(live_graph, resolve_place(PlaceItem(country="DE", area="Hamburg")))
    row = graph_own_posts.post_owner("acct:ada", pid)
    assert (row["place_country"], row["place_area"]) == ("DE", "Hamburg")
    q24 = live_graph.driver().execute_query(graph_own_posts.OWN_POST, me="acct:ada", id=pid,
                                            database_=live_graph.database()).records[0]
    assert (q24["place_country"], q24["place_area"]) == ("DE", "Hamburg")
    # With the switch unset an edit passes no place: the post keeps the one it has.
    assert edit(pid, live_graph, None)
    assert place_of(live_graph, pid)["area_key"] == "hamburg"
    assert edit(pid, live_graph, resolve_place(PlaceItem(country="DE", area="Bremen")))
    assert place_of(live_graph, pid) | {"keys": None} == {"country": "DE", "area": "Bremen", "area_key": "bremen",
                                                          "keys": None}
    # Changed to "Not about one place": the three go.
    assert edit(pid, live_graph, resolve_place(PlaceItem()))
    assert not {"place_country", "place_area"} & set(place_of(live_graph, pid)["keys"])


def test_export_and_restore_carry_the_place(live_graph):
    placed = post(live_graph, resolve_place(PlaceItem(country="GB", area="Leeds")))
    plain = post(live_graph, None, text="Another statement about the river.")
    before = place_of(live_graph, placed), place_of(live_graph, plain)
    exported = json.loads(json.dumps(live_graph.export_record()))
    validate_record(exported)
    node = next(n for n in exported["nodes"] if n["identity"] == placed)
    assert {k: node["properties"][k] for k in ("place_country", "place_area", "place_area_key")} == {
        "place_country": "GB", "place_area": "Leeds", "place_area_key": "leeds"}
    live_graph.driver().execute_query("MATCH (n) DETACH DELETE n", database_=live_graph.database())
    live_graph.restore_record(exported)
    assert (place_of(live_graph, placed), place_of(live_graph, plain)) == before


def test_the_two_place_indexes_are_made_only_with_the_switch(live_graph):
    def found():
        rows = live_graph.driver().execute_query("SHOW INDEXES YIELD name, properties RETURN name, properties",
                                                 database_=live_graph.database()).records
        return {row["name"]: row["properties"] for row in rows}
    # Wiping the nodes leaves indexes, so an earlier run with the switch on may have left these two behind.
    for name in ("post_place_country", "post_place_area"):
        live_graph.driver().execute_query(f"DROP INDEX {name} IF EXISTS", database_=live_graph.database())
    live_graph.ensure_constraints()  # as startup runs it with the switch unset
    assert not {"post_place_country", "post_place_area"} & set(found())
    live_graph.ensure_constraints(places=True)
    live_graph.ensure_constraints(places=True)  # idempotent
    assert found()["post_place_country"] == ["place_country"] and found()["post_place_area"] == ["place_area_key"]
