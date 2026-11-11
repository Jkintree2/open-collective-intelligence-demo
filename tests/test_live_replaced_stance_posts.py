"""John, 10 November 2026: a post whose only tie to a solution is its stance dropped off the solution's page and its
issue's page once its writer took the opposite stance (one stance per person, D7, deletes the old edge), or once a
later post said the same stance (last_post_id moves on). The post's stored card still says it, so both pages list it.
Live: the disposable Neo4j only."""

import json
from datetime import datetime, timezone

import pytest

from app import graph_item_pages, graph_own_posts
from app.extract import CardPayload, resolve_payload

pytestmark = pytest.mark.live
ISSUE = "Building a platform for digital democracy"
CONSENSUS = "Decisions should be made by consensus"
SOLUTION_KEY = "decisions should be made by consensus"
ISSUE_KEY = "building a platform for digital democracy"


def card(graph, stance, solution=CONSENSUS, issue=ISSUE):
    return resolve_payload(CardPayload.model_validate({
        "issues": [{"name": issue}], "solutions": [{"name": solution, "for_issue": issue, "stance": stance}]}),
        graph.candidates())


def post(graph, person, text, stance, anonymous=False, **names):
    name = None if anonymous else person.split(":")[1].capitalize()
    return graph.merge_post(person, name, anonymous, name, text, card(graph, stance, **names), one_stance=True)


def listed(graph):
    return ([row["id"] for row in graph_item_pages.solution_posts(SOLUTION_KEY)],
            [row["id"] for row in graph.issue_posts(ISSUE_KEY)])


def test_johns_case_every_post_stays_listed(live_graph):
    proposed = post(live_graph, "acct:bob", "Decide by consensus", "approve")
    named = post(live_graph, "acct:john", "I approve of consensus", "approve")
    hidden = post(live_graph, "acct:john", "Majority votes and Robert's Rules", "oppose", anonymous=True)
    assert graph_own_posts.edit_own_post("acct:john", named, card(live_graph, "approve"), text="I approve, edited",
                                         source="manual", extraction_raw=None, model=None, latency_ms=None,
                                         now=datetime.now(timezone.utc))
    on_solution, on_issue = listed(live_graph)
    assert set(on_solution) == set(on_issue) == {proposed, named, hidden}
    row = next(row for row in graph_item_pages.solution_posts(SOLUTION_KEY) if row["id"] == hidden)
    assert row["anonymous"] is True and row["display_name"] is None


def test_ask_on_the_solution_reads_the_post_too(live_graph):
    # John's second email that day: asked on the solution, "Do any statements say anything about majority votes?"
    # got "No statement in the database speaks of majority votes", since Ask reads the posts Q51 lists.
    from app import ask
    post(live_graph, "acct:bob", "Decide by consensus", "approve")
    post(live_graph, "acct:john", "I approve of consensus", "approve")
    post(live_graph, "acct:john", "Majority votes and Robert's Rules", "oppose", anonymous=True)
    post(live_graph, "acct:john", "Consensus after all", "approve")
    digest = json.loads(ask.solution_digest(SOLUTION_KEY).text)
    hidden = [row for row in digest["posts"] if "Robert's Rules" in row["text"]]
    assert [(row["by"], row.get("stances")) for row in hidden] == [("Anonymous", None)]


def test_a_post_whose_stance_was_replaced_by_the_writers_next_post_stays(live_graph):
    post(live_graph, "acct:bob", "Decide by consensus", "approve")
    first = post(live_graph, "acct:ada", "Consensus, yes", "approve")
    post(live_graph, "acct:ada", "On second thought, no", "oppose")
    on_solution, on_issue = listed(live_graph)
    assert first in on_solution and first in on_issue


def test_the_middle_post_that_said_the_same_stance_stays(live_graph):
    post(live_graph, "acct:bob", "Decide by consensus", "approve")
    posts = [post(live_graph, "acct:ada", f"Consensus, {n}", "approve") for n in ("yes", "still yes", "yes again")]
    on_solution, on_issue = listed(live_graph)
    assert set(posts) <= set(on_solution) and set(posts) <= set(on_issue)


def test_a_stance_on_another_solution_is_not_listed(live_graph):
    post(live_graph, "acct:bob", "Decide by consensus", "approve")
    post(live_graph, "acct:bob", "Majority rule", "approve", solution="Decisions by majority rule")
    elsewhere = post(live_graph, "acct:ada", "Majority, yes", "approve", solution="Decisions by majority rule")
    post(live_graph, "acct:ada", "Majority, no", "oppose", solution="Decisions by majority rule")
    assert elsewhere not in listed(live_graph)[0]
    post(live_graph, "acct:bob", "Rent caps", "approve", solution="Rent caps", issue="Housing")
    housing = post(live_graph, "acct:ada", "Caps, yes", "approve", solution="Rent caps", issue="Housing")
    post(live_graph, "acct:ada", "Caps, no", "oppose", solution="Rent caps", issue="Housing")
    assert housing not in listed(live_graph)[1]
    assert housing in [row["id"] for row in live_graph.issue_posts("housing")]


def test_the_limit_still_holds(live_graph):
    post(live_graph, "acct:bob", "Decide by consensus", "approve")
    post(live_graph, "acct:ada", "Consensus, yes", "approve")
    post(live_graph, "acct:ada", "Consensus, no", "oppose")
    assert len(graph_item_pages.solution_posts(SOLUTION_KEY, limit=2)) == 2
    assert len(live_graph.issue_posts(ISSUE_KEY, limit=2)) == 2


def test_a_typo_edit_keeps_the_post_on_the_solution_page(live_graph):
    """Review, 11 November 2026: the edit card holds only the stances the post's edges still carry, so a typo fix on
    a post whose stance was taken over saved a card without it, and the post fell off the solution's page again."""
    from app.routes_own_posts import current_card, kept_positions, resolve_edit
    post(live_graph, "acct:bob", "Decide by consensus", "approve")
    first = post(live_graph, "acct:ada", "Consensus, yes", "approve")
    post(live_graph, "acct:ada", "On second thought, no", "oppose")
    row = graph_own_posts.post_owner("acct:ada", first)
    shown, own = current_card(first, row["payload"])
    assert shown["solutions"] == []  # the stance it took is not on its edit card
    resolved, _ = resolve_edit(CardPayload.model_validate(shown), own)
    assert graph_own_posts.edit_own_post("acct:ada", first, resolved, text="Consensus, yes!", source="manual",
                                         extraction_raw=None, model=None, latency_ms=None,
                                         now=datetime.now(timezone.utc),
                                         payload_json=kept_positions(row["payload"], shown, resolved))
    on_solution, on_issue = listed(live_graph)
    assert first in on_solution and first in on_issue
    # Nothing was written to the stances: Ada still opposes, once.
    assert [(r["approves"], r["opposes"]) for r in [graph_item_pages.solution(SOLUTION_KEY)]] == [(1, 1)]
