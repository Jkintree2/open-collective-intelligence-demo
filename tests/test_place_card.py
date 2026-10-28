"""Phase 3, W3b: a place on each post, from the card's Place row (03_schema.md and 04_interface.md, "A place
on each post", "A place on the card"). Posting and editing write it only with PLACES_ENABLED; unset, a place
in the request is ignored and an edit leaves the post's place as it is. No database."""

from datetime import datetime, timezone

import pytest

from app.backup import InvalidBackup, properties
from app.extract import Candidates
from app.payload import NO_PLACE, PlaceItem, place_needs_country, resolve_place

CARD = {"text": "The river floods every spring.", "issues": [{"name": "River flooding"}]}
NEEDS_COUNTRY = "Please choose the country for this town or area."


def test_a_place_is_a_code_an_area_kept_only_with_a_country_and_its_key():
    assert resolve_place(PlaceItem(country="US", area="  St. Louis ")) == {
        "place_country": "US", "place_area": "St. Louis", "place_area_key": "st louis"}
    # A name or an alias is read as its code, as places.country_code() reads an account's country.
    assert resolve_place(PlaceItem(country="Germany"))["place_country"] == "DE"
    assert resolve_place(PlaceItem(country="usa", area=""))["place_area"] is None
    assert len(resolve_place(PlaceItem(country="DE", area="x" * 120))["place_area"]) == 80
    # "Not about one place", an unknown country, or no row: no place at all, the town included.
    for item in (PlaceItem(), PlaceItem(country="", area="Springfield"), PlaceItem(country="Atlantis"), None):
        assert resolve_place(item) == NO_PLACE
    # A town with no key of its own is kept as typed, with no key.
    assert resolve_place(PlaceItem(country="FR", area="Y")) == {"place_country": "FR", "place_area": "Y",
                                                                 "place_area_key": None}


def test_a_town_with_no_country_needs_one():
    assert place_needs_country(PlaceItem(area="Springfield"))
    assert place_needs_country(PlaceItem(country="Atlantis", area="Springfield"))
    assert not place_needs_country(PlaceItem(country="US", area="Springfield"))
    assert not place_needs_country(PlaceItem(country=None, area="  "))
    assert not place_needs_country(None)
    # Junk from a hand made request is read as text or nothing, never an error.
    assert PlaceItem.model_validate({"country": 5, "area": ["x"]}) == PlaceItem()


@pytest.fixture
def places_on(member_app, switch, monkeypatch):
    monkeypatch.setattr(member_app.main.graph, "candidates", Candidates.empty)
    member_app.sign_in()
    switch(places_enabled=True)
    return member_app


def test_the_place_list_and_the_accounts_country(places_on):
    places_on.accounts["acct:ada"]["country"] = "U.S.A."
    answer = places_on.client.get("/api/place").json()
    assert answer["not_one_place"] == "Not about one place"
    assert answer["choices"][0] == ["AF", "Afghanistan"] and ["US", "United States"] in answer["choices"]
    assert answer["country"] == "US"
    places_on.accounts["acct:ada"]["country"] = "Somewhere else"
    assert places_on.client.get("/api/place").json()["country"] is None


def test_the_place_list_is_not_there_with_the_switch_off(member_app):
    member_app.sign_in()
    assert member_app.client.get("/api/place").status_code == 404


def test_posting_writes_the_place_from_the_card(places_on):
    result = places_on.client.post("/api/posts", json={**CARD, "place": {"country": "US", "area": "St. Louis"}})
    assert result.status_code == 201
    assert places_on.writes[0][1]["place"] == {"place_country": "US", "place_area": "St. Louis",
                                               "place_area_key": "st louis"}


def test_not_about_one_place_and_no_row_write_no_place(places_on, monkeypatch):
    from app.auth import PostSpacing
    for body in ({**CARD, "place": {"country": None, "area": None}}, CARD):
        monkeypatch.setattr(places_on.main, "post_spacing", PostSpacing())
        assert places_on.client.post("/api/posts", json=body).status_code == 201
    assert places_on.writes[0][1]["place"] == NO_PLACE
    assert places_on.writes[1][1]["place"] is None


def test_a_town_with_no_country_holds_the_post_back(places_on):
    body = {**CARD, "place": {"country": None, "area": "Springfield"}}
    preview = places_on.client.post("/api/preview", json=body).json()
    assert preview["valid"] is False and preview["dropped"] == []
    result = places_on.client.post("/api/posts", json=body)
    assert result.status_code == 422 and result.json() == {"message": NEEDS_COUNTRY}
    assert places_on.writes == []
    assert places_on.client.post("/api/preview", json={**body, "place": {"country": "US", "area": "Springfield"}}
                                 ).json()["valid"] is True


def test_with_the_switch_off_a_place_in_the_request_is_ignored(member_app, monkeypatch):
    monkeypatch.setattr(member_app.main.graph, "candidates", Candidates.empty)
    member_app.sign_in()
    body = {**CARD, "place": {"country": None, "area": "Springfield"}}
    assert member_app.client.post("/api/preview", json=body).json()["valid"] is True
    assert member_app.client.post("/api/posts", json=body).status_code == 201
    assert member_app.writes[0][1]["place"] is None


def test_the_write_page_loads_the_place_row_only_with_the_switch(member_app, switch):
    member_app.sign_in()
    assert "place.js" not in member_app.client.get("/").text
    switch(places_enabled=True)
    assert '<script src="/static/place.js?v=' in member_app.client.get("/").text


# Editing: the post's own place on the edit page (Q24), the edited place saved, kept when the switch is off.
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
MINE = {"id": "mine-1", "text": "My statement", "anonymous": False, "created_at": NOW, "mine": True,
        "payload": '{"issues": [{"key": "flooding", "name": "Flooding"}], "solutions": [], "evidence": []}',
        "place_country": "DE", "place_area": "Hamburg"}
ROWS = [{"rel": "CLAIM", "from_label": "Person", "from_key": None, "from_name": "Ada Tester",
         "to_label": "Issue", "to_key": "flooding", "to_name": "Flooding", "home_key": None}]


@pytest.fixture
def editing(member_app, switch, monkeypatch):
    monkeypatch.setattr("app.graph_own_posts.post_owner", lambda me, pid: dict(MINE) if pid == "mine-1" else None)
    g = member_app.main.graph
    monkeypatch.setattr(g, "candidates", Candidates.empty)
    monkeypatch.setattr(g, "post_structure", lambda ids: {"mine-1": ROWS} if ids == ["mine-1"] else {})
    monkeypatch.setattr(g, "issue_header", lambda key: {"key": "flooding", "name": "Flooding", "parent_key": None,
                                                         "parent_name": None, "children": []} if key == "flooding" else None)
    saved = []
    monkeypatch.setattr("app.graph_own_posts.edit_own_post", lambda me, pid, payload, **kw: not saved.append(kw))
    member_app.sign_in()
    member_app.saved, member_app.switch = saved, switch
    return member_app


def _edit_data(page: str) -> dict:
    import json
    start = page.index('<script id="edit-post" type="application/json">') + len('<script id="edit-post" type="application/json">')
    return json.loads(page[start:page.index("</script>", start)])


def test_the_edit_page_carries_the_posts_place_only_with_the_switch(editing):
    assert "place" not in _edit_data(editing.client.get("/posts/mine-1/edit").text)
    editing.switch(places_enabled=True)
    assert _edit_data(editing.client.get("/posts/mine-1/edit").text)["place"] == {"country": "DE", "area": "Hamburg"}


def test_saving_an_edit_writes_the_place_from_the_card(editing):
    editing.switch(places_enabled=True)
    body = {"text": "Flooding again", "issues": [{"name": "Flooding"}], "place": {"country": "DE", "area": "Bremen"}}
    assert editing.client.post("/api/posts/mine-1", json=body).status_code == 200
    assert editing.saved[0]["place"] == {"place_country": "DE", "place_area": "Bremen", "place_area_key": "bremen"}
    # A card with no Place row, or a save without JavaScript, keeps the post's place.
    assert editing.client.post("/api/posts/mine-1", json={**body, "place": None}).status_code == 200
    editing.client.post("/posts/mine-1/edit", data={"text": "Flooding again, typo fixed"})
    assert [kw["place"] for kw in editing.saved[1:]] == [None, None]
    refused = editing.client.post("/api/posts/mine-1", json={**body, "place": {"country": "", "area": "Bremen"}})
    assert refused.status_code == 422 and refused.json() == {"message": NEEDS_COUNTRY}
    assert editing.client.post("/api/posts/mine-1/preview", json={**body, "place": {"area": "Bremen"}}
                               ).json()["valid"] is False
    assert len(editing.saved) == 3


def test_with_the_switch_off_an_edit_keeps_the_place(editing):
    body = {"text": "Flooding again", "issues": [{"name": "Flooding"}], "place": {"country": None, "area": None}}
    assert editing.client.post("/api/posts/mine-1", json=body).status_code == 200
    assert editing.saved[0]["place"] is None


def test_a_copy_checks_the_place_properties():
    assert properties({"place_country": "US", "place_area": "St. Louis", "place_area_key": "st louis"})
    for bad in ({"place_country": "us"}, {"place_country": "USA"}, {"place_country": 1},
                {"place_area": "x" * 81}, {"place_area": ["x"]}, {"place_area_key": 5}):
        with pytest.raises(InvalidBackup):
            properties(bad)


def test_the_place_indexes_are_made_only_with_the_switch(monkeypatch):
    """Startup runs the schema statements; with PLACES_ENABLED unset the two place indexes are not among them."""
    import asyncio
    import importlib
    from types import SimpleNamespace

    from app import graph
    ran = []
    monkeypatch.setattr(graph, "driver", lambda: SimpleNamespace(execute_query=lambda q, **kw: ran.append(q)))
    monkeypatch.setattr(graph, "database", lambda: "neo4j")
    graph.ensure_constraints()
    assert ran == list(graph.CONSTRAINTS) and not any("place" in statement for statement in ran)
    ran.clear()
    graph.ensure_constraints(places=True)
    assert ran == list(graph.CONSTRAINTS + graph.PLACE_INDEXES)

    # The app's startup passes the switch.
    from dataclasses import replace
    main = importlib.import_module("app.main")
    asked = []
    monkeypatch.setattr(graph, "open_driver", lambda settings: None)
    monkeypatch.setattr(graph, "close_driver", lambda: None)
    monkeypatch.setattr(graph, "ensure_constraints", lambda places=False, asking=False: asked.append(places))

    async def start(enabled):
        monkeypatch.setattr(main, "settings", replace(main.settings, places_enabled=enabled))
        async with main.lifespan(main.app):
            pass
    asyncio.run(start(False)); asyncio.run(start(True))
    assert asked == [False, True]


# John, 28 October: the questions' key and index, like the places', are made only with their switch.
def test_the_question_indexes_are_made_only_with_the_ask_switch(monkeypatch):
    import asyncio
    import importlib
    from types import SimpleNamespace

    from app import graph
    ran = []
    monkeypatch.setattr(graph, "driver", lambda: SimpleNamespace(execute_query=lambda q, **kw: ran.append(q)))
    monkeypatch.setattr(graph, "database", lambda: "neo4j")
    graph.ensure_constraints()
    assert not any("Question" in statement for statement in ran)
    ran.clear()
    graph.ensure_constraints(asking=True)
    assert ran == list(graph.CONSTRAINTS + graph.QUESTION_INDEXES)

    from dataclasses import replace
    main = importlib.import_module("app.main")
    asked = []
    monkeypatch.setattr(graph, "open_driver", lambda settings: None)
    monkeypatch.setattr(graph, "close_driver", lambda: None)
    monkeypatch.setattr(graph, "ensure_constraints", lambda places=False, asking=False: asked.append(asking))

    async def start(enabled):
        monkeypatch.setattr(main, "settings", replace(main.settings, ask_enabled=enabled))
        async with main.lifespan(main.app):
            pass
    asyncio.run(start(False)); asyncio.run(start(True))
    assert asked == [False, True]
