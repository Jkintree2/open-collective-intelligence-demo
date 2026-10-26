"""Issue 29 on the disposable Neo4j: a page read as taking the other side from the writer's is stored on its
side, with the writer's statement on theirs; an edit rebuilds the same pair, a delete removes both, a copy
restores both, and the issue page and Ask the record never count the statement as a source."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import check, confidence, graph_ask, graph_evidence, graph_own_posts, sides
from app.backup import validate_record
from app.check import Check, kept_checks
from app.extract import CardPayload, resolve_payload
from app.routes_own_posts import current_card

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)
URL = "https://en.wikipedia.org/wiki/Climate_change"
QUOTE = "Present day climate change includes both global warming and its wider effects on weather."
CLAIM = "The rise in CO2 in the air is minuscule and the article proves nothing."
SAID = f"Climate change is overstated. {CLAIM} {URL}"
SOURCE = {"type": "reference", "primary": False, "published": "2026-10", "cites": True}
PAGE_KEY = "en wikipedia org wiki climate change"
CLAIM_KEY = "rise in co2 in the air is minuscule and the article proves nothing"


@pytest.fixture(autouse=True)
def empty_cache():
    check.cache.clear()
    yield
    check.cache.clear()


def card(stance="refutes", verdict="supports"):
    return CardPayload.model_validate({"issues": [{"name": "Climate change"}], "evidence": [
        {"name": "", "url": URL, "stance": stance, "about": "Climate change",
         "check": {"verdict": verdict, "quote": QUOTE}}]})


def read(verdict="supports", claim=CLAIM, statement=SAID):
    check.cache.put(check.cache_key(URL, "Climate change", statement),
                    Check(verdict, URL, quote=QUOTE, claim=claim, source=SOURCE, checked_at=NOW.isoformat()))


def checks_for(graph, sent, statement, stored=None):
    payload = resolve_payload(sent, graph.candidates())
    kept = kept_checks(sent.evidence, payload.evidence, statement, stored)
    return payload, sides.attach(payload.evidence, kept, lambda: graph.candidates().evidence_links.values())


def post(graph, sent=None, *, flag=True, statement=SAID, person="acct:ada"):
    sent = sent or card()
    payload, checks = checks_for(graph, sent, statement)
    return graph.merge_post(person, "Ada", False, "Ada", statement, payload, checks=checks if flag else None)


def run(graph, query, **params):
    return [record.data() for record in graph.driver().execute_query(query, database_=graph.database(), **params).records]


def stances(graph, post_id):
    return sorted((row["e"], row["url"] is not None, row["rel"], row["answers"]) for row in run(
        graph, "MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(:Issue) WHERE r.post_id = $id "
               "RETURN e.key AS e, e.url AS url, type(r) AS rel, r.answers AS answers", id=post_id))


def counts(graph):
    return run(graph, "MATCH (e:Evidence) WITH count(e) AS evidence MATCH ()-[s:SUBMIT]->() "
                      "RETURN evidence, count(s) AS submits")[0]


def test_the_page_is_stored_on_its_side_and_the_statement_on_the_writers(live_graph):
    read()
    post_id = post(live_graph)
    assert stances(live_graph, post_id) == [(PAGE_KEY, True, "SUPPORTS", None), (CLAIM_KEY, False, "REFUTES", PAGE_KEY)]
    page = run(live_graph, "MATCH (e:Evidence)-[r:SUPPORTS]->() WHERE r.post_id = $id RETURN properties(r) AS p",
               id=post_id)[0]["p"]
    assert (page["check"], page["check_quote"], page["check_claim"]) == ("supports", QUOTE, CLAIM)
    own = run(live_graph, "MATCH (e:Evidence {key: $key})-[r]->() RETURN properties(e) AS e, properties(r) AS r",
              key=CLAIM_KEY)[0]
    assert set(own["r"]) == {"post_id", "created_at", "answers"}  # no reading, no personal tick
    assert own["e"]["name"] == CLAIM.rstrip(".") and "url" not in own["e"] and "source_type" not in own["e"]
    assert counts(live_graph) == {"evidence": 2, "submits": 2}


@pytest.mark.parametrize("verdict", ["partly", "unclear"])
def test_partly_and_unclear_stay_one_piece_of_evidence_on_the_writers_side(live_graph, verdict):
    read(verdict=verdict)
    post_id = post(live_graph, card(verdict=verdict))
    assert stances(live_graph, post_id) == [(PAGE_KEY, True, "REFUTES", None)]


def test_a_reading_the_site_did_not_make_and_the_flag_off_stay_as_before(live_graph):
    post_id = post(live_graph)  # nothing in the cache: the card's reading is only a claim
    assert stances(live_graph, post_id) == [(PAGE_KEY, True, "REFUTES", None)]
    read()
    off = post(live_graph, flag=False, person="acct:bob")
    assert stances(live_graph, off) == [(PAGE_KEY, True, "REFUTES", None)]
    assert set(run(live_graph, "MATCH ()-[r:REFUTES]->() WHERE r.post_id = $id RETURN properties(r) AS p",
                   id=off)[0]["p"]) == {"post_id", "created_at"}


def payload_of(graph, post_id):
    return run(graph, "MATCH (p:Post {id: $id}) RETURN p.payload AS payload", id=post_id)[0]["payload"]


def test_an_edit_after_a_restart_rebuilds_the_same_pair_and_matching_the_page_removes_the_statement(live_graph):
    read()
    post_id = post(live_graph)
    check.cache.clear()  # a restart: only the record remembers the reading
    edit, _ = current_card(post_id, payload_of(live_graph, post_id), readings=True)
    assert [(e["stance"], e["check"]["verdict"]) for e in edit["evidence"]] == [("refutes", "supports")]
    sent = CardPayload.model_validate(edit)
    stored = {key: {**row, "url": URL} for key, row in graph_evidence.post_checks(post_id).items()}
    payload, checks = checks_for(live_graph, sent, SAID, stored)
    assert graph_own_posts.edit_own_post("acct:ada", post_id, payload, text=SAID, source="manual", extraction_raw=None,
                                         model=None, latency_ms=None, now=NOW + timedelta(hours=1), checks=checks)
    assert stances(live_graph, post_id) == [(PAGE_KEY, True, "SUPPORTS", None), (CLAIM_KEY, False, "REFUTES", PAGE_KEY)]
    assert counts(live_graph) == {"evidence": 2, "submits": 2}
    # The writer chooses the page's side: one piece of evidence, and the statement is gone.
    matched = CardPayload.model_validate({**edit, "evidence": [dict(edit["evidence"][0], stance="supports")]})
    payload, checks = checks_for(live_graph, matched, SAID, stored)
    assert graph_own_posts.edit_own_post("acct:ada", post_id, payload, text=SAID, source="manual", extraction_raw=None,
                                         model=None, latency_ms=None, now=NOW + timedelta(hours=2), checks=checks)
    assert stances(live_graph, post_id) == [(PAGE_KEY, True, "SUPPORTS", None)]
    assert counts(live_graph) == {"evidence": 1, "submits": 1}


def test_deleting_the_post_removes_both(live_graph):
    read()
    post_id = post(live_graph)
    assert graph_own_posts.delete_own_post("acct:ada", post_id)
    assert run(live_graph, "MATCH (e:Evidence) RETURN count(e) AS n")[0]["n"] == 0


def test_a_copy_restores_the_statement_with_what_it_answers(live_graph):
    read()
    post_id = post(live_graph)
    before = stances(live_graph, post_id)
    exported = json.loads(json.dumps(live_graph.export_record()))
    validate_record(exported)
    live_graph.driver().execute_query("MATCH (n) DETACH DELETE n", database_=live_graph.database())
    live_graph.restore_record(exported)
    assert stances(live_graph, post_id) == before


def test_the_issue_page_and_ask_never_count_the_statement_as_a_source(live_graph):
    read()
    post(live_graph)
    check.cache.clear()
    nasa = CardPayload.model_validate({"issues": [{"name": "Climate change"}], "evidence": [
        {"name": "NASA temperature record", "stance": "supports", "about": "Climate change"}]})
    post(live_graph, nasa, statement="It is warming.", person="acct:bob")
    rows = graph_evidence.issue_confidence("climate change")
    found = confidence.lines(rows, today=NOW.date())
    assert found[("issue", "climate change", PAGE_KEY, "SUPPORTS")]["words"].endswith(
        "One other piece of evidence here says the same.")
    assert found[("issue", "climate change", CLAIM_KEY, "REFUTES")]["answers"] == PAGE_KEY
    asked = {row["key"]: row["answers"] for row in graph_ask.issue_evidence("climate change")}
    assert asked == {PAGE_KEY: None, CLAIM_KEY: PAGE_KEY, "nasa temperature record": None}
