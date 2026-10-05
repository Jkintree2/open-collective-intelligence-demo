from datetime import datetime, timezone

import pytest

from app import graph_search, search

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

SETUP = """
CREATE (i:Issue {key: 'housing costs', name: 'Housing costs', seed: false, created_at: $now})
CREATE (f:Issue {key: 'flooding', name: 'Flooding', seed: false, created_at: $now})
CREATE (s:Solution {key: 'social housing', name: 'Social housing', seed: false, created_at: $now})
CREATE (i)-[:HAVE_PROPOSED {created_at: $now}]->(s)
CREATE (e:Evidence {key: 'report', name: 'Housing report', seed: false, created_at: $now})
CREATE (e)-[:SUPPORTS {created_at: $now}]->(s)
CREATE (:Person {key: 'acct:ada', name: 'Ada'})-[:POSTED {created_at: $now}]->
       (:Post {id: 'p1', text: 'Rent is rising on our housing estate', anonymous: false, display_name: 'Ada',
               seed: false, created_at: $now})
"""


def test_a_word_start_finds_names_and_posts(live_graph):
    live_graph.driver().execute_query(SETUP, now=NOW, database_=live_graph.database())
    query = search.lucene_query("hous")
    found = search.group(graph_search.search_names(query))
    assert [r["name"] for r in found["issues"]] == ["Housing costs"]
    assert found["solutions"] == [{"name": "Social housing", "href": "/issues/housing%20costs"}]
    assert found["evidence"] == [{"name": "Housing report", "href": "/issues/housing%20costs"}]
    assert [p["id"] for p in graph_search.search_posts(query)] == ["p1"]
    assert graph_search.search_names(search.lucene_query("zebra")) == []


def test_every_word_must_match(live_graph):
    """X4: the page says "Try another word, or fewer words", so a second word narrows the results."""
    live_graph.driver().execute_query(SETUP, now=NOW, database_=live_graph.database())
    one = search.group(graph_search.search_names(search.lucene_query("housing")))
    assert len(one["issues"]) + len(one["solutions"]) + len(one["evidence"]) == 3
    two = search.group(graph_search.search_names(search.lucene_query("housing costs")))
    assert [r["name"] for r in two["issues"]] == ["Housing costs"] and two["solutions"] == two["evidence"] == []
    assert graph_search.search_names(search.lucene_query("housing zebra")) == []
    assert graph_search.search_posts(search.lucene_query("housing zebra")) == []
    assert [p["id"] for p in graph_search.search_posts(search.lucene_query("rent housing"))] == ["p1"]


@pytest.mark.parametrize("typed", ['"unclosed', "a:b", "c++", "(", "AND", "NOT housing", "/", "\\", "~fuzzy",
                                   "housing~2", "x^3", "[a TO b]", "{x}", "?", "ho*ing"])
def test_awkward_searches_never_fail(live_graph, typed):
    """Item 28 of the 5 October review: graph_search swallows a refusal and finds nothing, so this
    runs the two queries through _read, where a refusal from Lucene would fail the test."""
    from app.graph_runtime import _read
    live_graph.driver().execute_query(SETUP, now=NOW, database_=live_graph.database())
    query = search.lucene_query(typed)
    if query is not None:
        assert isinstance(_read(graph_search.SEARCH_NAMES, query=query), list)
        assert isinstance(_read(graph_search.SEARCH_POSTS, query=query), list)
