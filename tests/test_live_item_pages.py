"""GitHub issue 55 (John, 30 October 2026): the solution and evidence pages' reads (Q50 to Q54), the Ask digests
on those pages, and a question kept on a solution, on the fixture record (seed plus tests/fixtures/ask_record.json).
Live: the disposable Neo4j only."""

import json
from datetime import date, datetime, timezone

import pytest

from app import ask, graph_item_pages, graph_questions
from scripts.asks import FIXTURE, load_fixture

pytestmark = pytest.mark.live
TAX = "global carbon tax by referendum"
DASHBOARD = "world bank carbon pricing dashboard"
CLIMATE = "global climate coordination"
TODAY = date(2026, 10, 30)
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
PRIVATE = json.loads(FIXTURE.read_text(encoding="utf-8"))["private"]
SET_PRIVATE = "MATCH (p:Person {key: $key}) SET p.email = $email, p.country = $country, p.postal_code = $postal_code"
ANSWER = {"paragraphs": [{"text": "Three oppose it.", "refs": [1]}], "partial": None,
          "sources": [{"id": "S1", "kind": "solution", "name": "Global carbon tax by referendum", "date": None,
                       "text": None, "href": "/issues/global%20climate%20coordination",
                       "issue": "Global climate coordination", "post_id": None,
                       "page": "/solutions/global%20carbon%20tax%20by%20referendum"}]}


@pytest.fixture
def record(live_graph):
    load_fixture()
    for key, details in PRIVATE.items():
        live_graph.driver().execute_query(SET_PRIVATE, key=key, **details, database_=live_graph.database())
    live_graph.driver().execute_query("CALL db.awaitIndexes(60)", database_=live_graph.database())
    return live_graph


def test_q50_a_solution_with_its_issue_proposers_stances_and_evidence(record):
    tax = graph_item_pages.solution(TAX, me="acct:ada")
    assert tax["issues"] == [{"key": CLIMATE, "name": "Global climate coordination",
                              "parent_key": "need for world government", "parent_name": "Need for world government"}]
    assert (tax["proposers"], tax["proposed_by"]) == (1, ["John Kintree"])
    assert (tax["approves"], tax["opposes"], tax["my_stance"]) == (4, 3, "APPROVE")
    assert tax["evidence"] == [{"key": "study of who pays carbon taxes", "name": "Study of who pays carbon taxes",
                                "url": "https://example.org/carbon-tax-incidence", "stance": "REFUTES"}]
    assert graph_item_pages.solution(TAX)["my_stance"] is None
    assert graph_item_pages.solution("no such solution") is None


def test_q51_the_posts_that_mention_a_solution_newest_first(record):
    # ask-08 said Ada's approval again (last_post_id); the seed posts proposed it.
    assert [post["id"] for post in graph_item_pages.solution_posts(TAX)] == \
        ["ask-08", "ask-07", "ask-05", "ask-03", "ask-02", "ask-01", "seed-11", "seed-09"]
    assert len(graph_item_pages.solution_posts(TAX, limit=2)) == 2


def test_q52_evidence_with_what_it_speaks_to_and_the_evidence_on_it(record):
    dashboard = graph_item_pages.evidence(DASHBOARD)
    assert dashboard["url"] == "https://carbonpricingdashboard.worldbank.org/"
    assert dashboard["targets"] == [{"kind": "issue", "key": CLIMATE, "name": "Global climate coordination",
                                     "stance": "SUPPORTS", "home_key": None, "home_name": None,
                                     "parent_key": "need for world government",
                                     "parent_name": "Need for world government"}]
    assert [(item["name"], item["stance"]) for item in dashboard["evidence"]] == [
        ("IMF proposal for an international carbon price floor", "SUPPORTS"),
        ("OECD Effective Carbon Rates 2023", "SUPPORTS")]
    # No link, given as personal experience, about a solution under its issue.
    steel = graph_item_pages.evidence("our steel plant closing")
    assert (steel["url"], steel["personal"], steel["submitted_by"]) == (None, True, ["Eli Novak"])
    assert [(t["kind"], t["name"], t["home_key"]) for t in steel["targets"]] == \
        [("solution", "Carbon border adjustment", CLIMATE)]
    assert graph_item_pages.evidence("no such evidence") is None


def test_q53_and_q54_the_posts_and_the_rows_for_agreement(record):
    assert [post["id"] for post in graph_item_pages.evidence_posts(DASHBOARD)] == ["ask-07", "ask-06", "seed-11"]
    rows = graph_item_pages.evidence_confidence("study of who pays carbon taxes")
    study = next(row for row in rows if row["evidence_key"] == "study of who pays carbon taxes")
    assert (study["target_kind"], study["target_key"], study["stance"], study["check"]) == \
        ("solution", TAX, "REFUTES", "partly")
    assert study["source_known"] is True and study["source_published"] == "2019"


def test_an_anonymous_proposer_or_submitter_is_never_named(live_graph):
    live_graph.driver().execute_query("""
        CREATE (p:Person {key: 'acct:hidden', name: 'Hidden Name'})
        CREATE (p)-[:PROPOSE {anonymous: true, post_id: 'x1', created_at: datetime()}]->
               (s:Solution {key: 'a plan', name: 'A plan', created_at: datetime()})
        CREATE (p)-[:SUBMIT {anonymous: true, post_id: 'x1', created_at: datetime()}]->
               (e:Evidence {key: 'a paper', name: 'A paper', created_at: datetime()})
        CREATE (p)-[:PROPOSE {anonymous: false, post_id: 'x2', created_at: datetime()}]->(s)
        CREATE (e)-[:SUPPORTS {post_id: 'x1', created_at: datetime()}]->(s)
        """, database_=live_graph.database())
    plan = graph_item_pages.solution("a plan")
    # Counted by account and anonymity (D2): the named and the anonymous proposal are two.
    assert plan["proposers"] == 2 and sorted(plan["proposed_by"]) == ["Anonymous", "Hidden Name"]
    paper = graph_item_pages.evidence("a paper")
    assert paper["submitted_by"] == ["Anonymous"]
    assert paper["targets"][0]["kind"] == "solution" and paper["targets"][0]["home_key"] is None


def test_the_solution_digest_reads_the_solution_and_the_posts_about_it(record):
    built = ask.solution_digest(TAX, today=TODAY)
    body = json.loads(built.text)
    assert body["asked_about"] == "the solution Global carbon tax by referendum"
    assert [item["name"] for item in body["issues"]] == ["Global climate coordination"]
    assert [(s["id"], s["approved_by"], s["opposed_by"]) for s in body["solutions"]] == [("S1", 4, 3)]
    assert [e["name"] for e in body["evidence"]] == ["Study of who pays carbon taxes"]
    assert built.posts_in == 8 and built.posts_left_out == 0
    assert built.sources["S1"].page == "/solutions/global%20carbon%20tax%20by%20referendum"
    assert built.sources["E1"].page == "/evidence/study%20of%20who%20pays%20carbon%20taxes"
    assert built.sources["P1"].href == "/issues/global%20climate%20coordination"
    assert ask.solution_digest("no such solution") is None


def test_the_evidence_digest_reads_the_evidence_on_it(record):
    built = ask.evidence_digest(DASHBOARD, today=TODAY)
    body = json.loads(built.text)
    assert body["asked_about"] == "the evidence World Bank Carbon Pricing Dashboard"
    first = body["evidence"][0]
    assert first["name"] == "World Bank Carbon Pricing Dashboard" and first["supported_by"] == ["E2", "E3"]
    assert "solutions" not in body and built.posts_in == 3
    assert built.sources["E1"].page == "/evidence/world%20bank%20carbon%20pricing%20dashboard"
    assert ask.evidence_digest("no such evidence") is None


def test_the_new_digests_never_hold_a_private_detail_or_a_hidden_name(record):
    for built in (ask.solution_digest(TAX, today=TODAY), ask.solution_digest("carbon border adjustment"),
                  ask.evidence_digest(DASHBOARD), ask.evidence_digest("study of who pays carbon taxes")):
        assert all(value not in built.text for details in PRIVATE.values() for value in details.values())
        assert "Gil Santos" not in built.text and "acct:" not in built.text


def test_a_question_on_a_solution_is_kept_and_listed_on_its_page_only(record):
    record.ensure_constraints(asking=True)
    on_tax = graph_questions.keep("Who pays?", None, NOW, ANSWER, solution_key=TAX)
    on_climate = graph_questions.keep("Who pays?", CLIMATE, NOW, ANSWER)
    on_dashboard = graph_questions.keep("Who pays?", None, NOW, ANSWER, evidence_key=DASHBOARD)
    assert len({on_tax, on_climate, on_dashboard}) == 3
    listed = graph_questions.recent(None, 5, solution_key=TAX)
    assert [(row["id"], row["solution_name"], row["issue_key"]) for row in listed] == \
        [(on_tax, "Global carbon tax by referendum", None)]
    assert [row["id"] for row in graph_questions.recent(CLIMATE, 5)] == [on_climate]
    assert [row["evidence_name"] for row in graph_questions.recent(None, 5, evidence_key=DASHBOARD)] == \
        ["World Bank Carbon Pricing Dashboard"]
    assert len(graph_questions.recent()) == 3
    kept = graph_questions.one(on_tax)
    assert (kept["solution_key"], kept["solution_name"], kept["answer"]) == (TAX, "Global carbon tax by referendum", ANSWER)
