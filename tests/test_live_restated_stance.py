"""John, 9 November 2026: a post that takes again a stance its writer already holds, on a solution already under
the issue the card names, writes no edge of its own (GitHub issue 4 drops the issue; the stance edge only takes the
post as last_post_id). Its buttons and "show what was added" still name the solution, and the issue the card named
while the solution is still under it, as the issue and solution pages already list the post.
Live: the disposable Neo4j only."""

import importlib

import pytest

from app.config import Settings
from app.extract import CardPayload, resolve_payload

pytestmark = pytest.mark.live
TAX = {"name": "Global carbon tax", "for_issue": "Climate change", "stance": "approve"}


def card(graph, **fields):
    return resolve_payload(CardPayload.model_validate(fields), graph.candidates())


def post(graph, person, text, anonymous=False, **fields):
    name = None if anonymous else person.split(":")[1].capitalize()
    return graph.merge_post(person, name, anonymous, name, text, card(graph, **fields), one_stance=True)


@pytest.fixture
def main(live_graph, monkeypatch):
    # app.main reads its settings on import; these are never used to open anything.
    monkeypatch.setattr("app.config.get_settings", lambda: Settings("unused", "unused", "unused", "neo4j://x", "neo4j", "x"))
    return importlib.import_module("app.main")


def decorated(main, post_id):
    return main._decorate_posts([{"id": post_id, "created_at": None}])[0]


def test_approving_again_shows_the_solution_and_the_issue_named(live_graph, main):
    first = post(live_graph, "acct:ada", "Tax carbon", issues=[{"name": "Climate change"}], solutions=[TAX])
    again = post(live_graph, "acct:ada", "Still for the tax", issues=[{"name": "Climate change"}], solutions=[TAX])
    owned = live_graph.driver().execute_query("MATCH ()-[r]->() WHERE r.post_id = $id RETURN count(r) AS n", id=again,
                                              database_=live_graph.database()).records[0]["n"]
    assert owned == 0  # John's case: the post wrote nothing of its own
    later = decorated(main, again)
    assert [(chip["label"], chip["name"]) for chip in later["chips"]] == [
        ("Issue", "Climate change"), ("Solution", "Global carbon tax")]
    assert later["sentences"] == ["Ada approves Global carbon tax"]
    # The first post keeps its own buttons and lines.
    earlier = decorated(main, first)
    assert {chip["name"] for chip in earlier["chips"]} == {"Climate change", "Global carbon tax"}
    assert "Ada approves Global carbon tax" in earlier["sentences"]


def test_an_anonymous_post_that_approves_again_never_shows_the_name(live_graph, main):
    post(live_graph, "acct:ada", "Tax carbon", issues=[{"name": "Climate change"}], solutions=[TAX])
    hidden = post(live_graph, "acct:ada", "Still for it", anonymous=True, issues=[{"name": "Climate change"}],
                  solutions=[TAX])
    assert decorated(main, hidden)["sentences"] == ["Anonymous approves Global carbon tax"]


def test_the_issue_named_shows_only_while_the_solution_is_under_it(live_graph, main):
    post(live_graph, "acct:ada", "Tax carbon", issues=[{"name": "Climate change"}], solutions=[TAX])
    post(live_graph, "acct:bob", "Rent", issues=[{"name": "Housing"}])
    # Housing never proposed the tax, so this post's card proposes it there: its own edges, as before.
    there = post(live_graph, "acct:ada", "Tax for housing", issues=[{"name": "Housing"}],
                 solutions=[{**TAX, "for_issue": "Housing"}])
    assert {chip["name"] for chip in decorated(main, there)["chips"]} == {"Housing", "Global carbon tax"}
    again = post(live_graph, "acct:ada", "Tax again", issues=[{"name": "Climate change"}], solutions=[TAX])
    live_graph.driver().execute_query("MATCH (:Issue {key: 'climate change'})-[r:HAVE_PROPOSED]->() DELETE r",
                                      database_=live_graph.database())
    assert [chip["name"] for chip in decorated(main, again)["chips"]] == ["Global carbon tax"]


def test_the_edit_card_still_leaves_out_a_stance_held_before_the_post(live_graph, main):
    from app import routes_own_posts
    post(live_graph, "acct:ada", "Tax carbon", issues=[{"name": "Climate change"}], solutions=[TAX])
    again = post(live_graph, "acct:ada", "Still for the tax", issues=[{"name": "Climate change"}], solutions=[TAX])
    stored = live_graph.driver().execute_query("MATCH (p:Post {id: $id}) RETURN p.payload AS payload", id=again,
                                               database_=live_graph.database()).records[0]["payload"]
    edit, own = routes_own_posts.current_card(again, stored)
    assert edit == {"issues": [], "solutions": [], "evidence": []} and own == {}
