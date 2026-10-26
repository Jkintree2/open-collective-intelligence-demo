"""Phase 3, places in the record (W4), on the disposable Neo4j: Q43 (issues near a place, the prefill) and Q44
(places of a page of posts). Posts are written through the write path; their place properties are set
straight onto them, as W3b's card will write them."""

import importlib
from datetime import datetime, timedelta, timezone

import pytest

from app import graph_places, places
from app.config import Settings
from app.extract import CardPayload, resolve_payload

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
SET_PLACE = """
MATCH (post:Post {id: $id})
SET post.place_country = $country, post.place_area = $area, post.place_area_key = $area_key
"""


def post(graph, person, text, *, minutes=0, anonymous=False, country=None, area=None, **fields):
    name = None if anonymous else person.split(":")[1].capitalize()
    card = resolve_payload(CardPayload.model_validate(fields), graph.candidates())
    post_id = graph.merge_post(person, name, anonymous, name, text, card, created_at=NOW + timedelta(minutes=minutes))
    if country:
        area = places.clean_area(area)
        graph.driver().execute_query(SET_PLACE, id=post_id, country=country, area=area, area_key=places.area_key(area),
                                     database_=graph.database())
    return post_id


def test_places_of_a_page_of_posts(live_graph):
    town = post(live_graph, "acct:ada", "Rents rose", country="US", area="St. Louis", issues=[{"name": "Rent"}])
    land = post(live_graph, "acct:bob", "The veto", country="DE", issues=[{"name": "Veto"}])
    none = post(live_graph, "acct:cy", "Floods", issues=[{"name": "Flooding"}])
    found = graph_places.post_places([town, land, none, "no such post"])
    assert found == {town: {"id": town, "country": "US", "area": "St. Louis"},
                     land: {"id": land, "country": "DE", "area": None}}
    assert places.place_text(found[town]["country"], found[town]["area"]) == "St. Louis, United States"
    assert graph_places.post_places([]) == {}


def test_near_by_area_matches_the_key_and_by_country_every_area(live_graph):
    post(live_graph, "acct:ada", "Rents rose", country="US", area="St. Louis", issues=[{"name": "Rent"}])
    post(live_graph, "acct:bob", "Lead pipes", country="US", area="st louis", issues=[{"name": "Lead pipes"}])
    post(live_graph, "acct:cy", "Heat waves", country="US", area="Phoenix", issues=[{"name": "Heat"}])
    post(live_graph, "acct:di", "Bus fares", country="US", issues=[{"name": "Bus fares"}])
    post(live_graph, "acct:ed", "The veto", country="DE", area="St. Louis", issues=[{"name": "Veto"}])
    post(live_graph, "acct:fay", "Rent again", issues=[{"name": "Flooding"}])
    assert graph_places.issues_near("US", "st louis") == {"rent", "lead pipes"}
    assert graph_places.issues_near("US", None) == {"rent", "lead pipes", "heat", "bus fares"}
    assert graph_places.issues_near("DE", None) == {"veto"}
    assert graph_places.issues_near("FR", None) == set()
    assert graph_places.issues_near("US", "springfield") == set()


def test_a_stance_on_a_solution_makes_its_issue_near(live_graph):
    post(live_graph, "acct:ada", "Seawalls for floods", issues=[{"name": "Flooding"}],
         solutions=[{"name": "Seawalls", "for_issue": "Flooding"}])
    bob = post(live_graph, "acct:bob", "I back seawalls", country="NL", area="Rotterdam",
               solutions=[{"name": "Seawalls", "for_issue": "Flooding", "stance": "approve"}])
    touching = live_graph.driver().execute_query(
        "MATCH (:Issue)-[r]-() WHERE r.post_id = $id RETURN count(r) AS n", id=bob,
        database_=live_graph.database()).records[0]["n"]
    stance = live_graph.driver().execute_query(
        "MATCH (:Person)-[r:APPROVE]->(:Solution {key: 'seawalls'}) WHERE r.post_id = $id RETURN count(r) AS n",
        id=bob, database_=live_graph.database()).records[0]["n"]
    assert touching == 0 and stance == 1   # only the stance carries Bob's post
    assert graph_places.issues_near("NL", "rotterdam") == {"flooding"}


def test_a_near_sub_issue_shows_under_its_parent_with_whole_counts(live_graph, monkeypatch):
    # app.main reads its settings on import; these are never used to open anything.
    monkeypatch.setattr("app.config.get_settings", lambda: Settings("unused", "unused", "unused", "neo4j://x", "neo4j", "x"))
    main = importlib.import_module("app.main")
    post(live_graph, "acct:ada", "Floods", issues=[{"name": "Flooding"}])
    post(live_graph, "acct:bob", "Coastal floods", issues=[{"name": "Coastal floods", "parent": "Flooding"}])
    post(live_graph, "acct:cy", "Berlin floods", country="DE", area="Berlin",
         issues=[{"name": "Floods in Berlin", "parent": "Flooding"}])
    post(live_graph, "acct:di", "Rent", issues=[{"name": "Rent"}])
    keys = graph_places.issues_near("DE", "berlin")
    assert "floods in berlin" in keys and "rent" not in keys and "coastal floods" not in keys
    full = live_graph.group_issues(live_graph.list_issues(), "people")
    near = main._only_near(full, keys)
    assert [(i["name"], [c["name"] for c in i["children"]]) for i in near] == [("Flooding", ["Floods in Berlin"])]
    flooding = next(i for i in full if i["key"] == "flooding")
    assert (near[0]["people"], near[0]["claims"]) == (flooding["people"], flooding["claims"]) == (3, 3)


def test_the_prefill_is_the_members_newest_placed_post(live_graph):
    assert graph_places.last_place("acct:ada") is None
    post(live_graph, "acct:ada", "Rents rose", minutes=1, country="US", area="St. Louis", issues=[{"name": "Rent"}])
    post(live_graph, "acct:ada", "Quietly", minutes=2, anonymous=True, country="DE", area="Berlin",
         issues=[{"name": "Veto"}])
    post(live_graph, "acct:ada", "No place", minutes=3, issues=[{"name": "Heat"}])
    post(live_graph, "acct:bob", "Elsewhere", minutes=4, country="FR", issues=[{"name": "Heat"}])
    # The anonymous post counts: it is Ada's own place, shown only to her.
    assert graph_places.last_place("acct:ada") == {"country": "DE", "area": "Berlin"}
    assert graph_places.last_place("acct:bob") == {"country": "FR", "area": None}
    assert graph_places.last_place("acct:nobody") is None


# The first Q43 (26 October): every issue against every collected post id. Kept as the reference the
# post-first Q43 must agree with.
FIRST_Q43 = """
MATCH (post:Post)
WHERE post.place_country = $country
  AND ($area_key IS NULL OR post.place_area_key = $area_key)
WITH collect(post.id) AS ids
MATCH (i:Issue)
WHERE EXISTS { MATCH (i)-[r]-() WHERE r.post_id IN ids }
   OR EXISTS { MATCH (i)-[:HAVE_PROPOSED]->(:Solution)<-[r:APPROVE|OPPOSE]-(:Person)
               WHERE r.post_id IN ids OR r.last_post_id IN ids }
RETURN i.key AS key
"""


def test_post_first_q43_finds_what_the_first_one_found(live_graph):
    from app.graph_runtime import _read
    post(live_graph, "acct:ada", "Floods and rent", issues=[{"name": "Flooding"}, {"name": "Rent"}],
         solutions=[{"name": "Seawalls", "for_issue": "Flooding"}])
    post(live_graph, "acct:bob", "Berlin floods", country="DE", area="Berlin",
         issues=[{"name": "Floods in Berlin", "parent": "Flooding"}])
    # A proposal only, for an issue the post does not claim.
    post(live_graph, "acct:cy", "Rent caps", country="DE", area="Berlin",
         solutions=[{"name": "Rent caps", "for_issue": "Rent"}])
    # Evidence only, about an issue the post does not claim.
    ev = post(live_graph, "acct:di", "A report", country="DE", area="Hamburg",
              evidence=[{"name": "Flood report", "about": "Flooding", "stance": "supports"}])
    # A stance by an unplaced post, then taken again by a placed one (last_post_id).
    post(live_graph, "acct:ed", "Seawalls yes", solutions=[{"name": "Seawalls", "for_issue": "Flooding", "stance": "approve"}])
    post(live_graph, "acct:ed", "Seawalls still", country="DE", area="Munich", minutes=5,
         solutions=[{"name": "Seawalls", "for_issue": "Flooding", "stance": "approve"}])
    post(live_graph, "acct:fay", "Heat", country="FR", issues=[{"name": "Heat"}])
    supports = live_graph.driver().execute_query(
        "MATCH (:Evidence)-[r:SUPPORTS]->(:Issue {key: 'flooding'}) WHERE r.post_id = $id RETURN count(r) AS n",
        id=ev, database_=live_graph.database()).records[0]["n"]
    assert supports == 1
    for country, area_key in (("DE", None), ("DE", "berlin"), ("DE", "hamburg"), ("DE", "munich"),
                              ("FR", None), ("US", None)):
        first = {row["key"] for row in _read(FIRST_Q43, country=country, area_key=area_key)}
        assert graph_places.issues_near(country, area_key) == first, (country, area_key)
    assert graph_places.issues_near("DE", "hamburg") == {"flooding"}
    assert graph_places.issues_near("DE", "munich") == {"flooding"}
    assert graph_places.issues_near("DE", "berlin") == {"floods in berlin", "flooding", "rent"}


def test_q43_reads_only_the_newest_placed_posts_and_caps_the_issues(live_graph, monkeypatch):
    post(live_graph, "acct:ada", "Old", minutes=1, country="DE", issues=[{"name": "Rent"}])
    post(live_graph, "acct:bob", "New", minutes=2, country="DE", issues=[{"name": "Heat"}, {"name": "Veto"}])
    monkeypatch.setattr(graph_places, "NEAR_POSTS", 1)
    assert graph_places.issues_near("DE", None) == {"heat", "veto"}
    monkeypatch.setattr(graph_places, "NEAR_ISSUES", 1)
    assert len(graph_places.issues_near("DE", None)) == 1
