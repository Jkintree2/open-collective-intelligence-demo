"""Issue 29: when this site read a page as taking the other side from the writer's, the post stores the page on
its side and the writer's statement on theirs. Only for a kept supports or refutes reading; with the flag off
the write path is Phase 1's. No network, no database."""

import importlib
import json
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import ask, backup, check, confidence, graph, graph_evidence, graph_posts, sides
from app.auth import MinuteBucket
from app.check import Check, kept_checks
from app.config import Settings
from app.extract import Candidates, CardPayload, resolve_payload
from app.routes_own_posts import edit_card
from app.text import sentences

URL = "https://en.wikipedia.org/wiki/Climate_change"
PAGE = "En.wikipedia.org/wiki/Climate_change"  # the name a row given only this link takes
PAGE_KEY = "en wikipedia org wiki climate change"
CLAIM_KEY = "rise in co2 in the air is minuscule and the article proves nothing"
FALLBACK_KEY = "statement on en wikipedia org wiki climate change"
QUOTE = "Present day climate change includes both global warming and its wider effects on weather."
CLAIM = "The rise in CO2 in the air is minuscule and the article proves nothing."
SAID = f"Climate change is overstated. {CLAIM} {URL}"
SOURCE = {"type": "reference", "primary": False, "published": "2026-10", "cites": True}
CARD = {"issues": [{"name": "Climate change"}],
        "evidence": [{"name": "", "url": URL, "stance": "refutes", "about": "Climate change",
                      "check": {"verdict": "supports", "quote": QUOTE}}]}


@pytest.fixture(autouse=True)
def empty_cache():
    check.cache.clear()
    yield
    check.cache.clear()


def remember(verdict="supports", quote=QUOTE, claim=CLAIM, statement=SAID):
    check.cache.put(check.cache_key(URL, "Climate change", statement),
                    Check(verdict, URL, quote=quote if verdict in check.QUOTED else None, claim=claim,
                          source=SOURCE, checked_at="2026-10-26T09:00:00+00:00"))


def resolved(card=CARD):
    sent = CardPayload.model_validate(card)
    return sent, resolve_payload(sent, Candidates.empty())


def kept(card=CARD, statement=SAID, linked=()):
    sent, payload = resolved(card)
    return sides.attach(payload.evidence, kept_checks(sent.evidence, payload.evidence, statement), lambda: linked), payload


def row(verdict, stance, **extra):
    return {**CARD, "evidence": [dict(CARD["evidence"][0], stance=stance, check={"verdict": verdict, "quote": QUOTE},
                                      **extra)]}


# Which rows split.

def test_a_page_read_as_supporting_under_a_writer_who_refutes_splits_with_the_writers_sentence_as_name():
    remember()
    checks, _ = kept()
    assert checks[PAGE_KEY]["statement"] == {
        "key": CLAIM_KEY, "name": "The rise in CO2 in the air is minuscule and the article proves nothing",
        "stance": "refutes", "page": "supports"}
    assert checks[PAGE_KEY]["check"] == "supports" and checks[PAGE_KEY]["check_claim"] == CLAIM


def test_without_the_writers_sentence_the_statement_is_named_after_the_page():
    remember(claim=None)
    checks, payload = kept()
    statement = sides.statements(checks)[payload.evidence[0]["key"]]
    assert statement["name"] == f"Statement on {PAGE}"
    assert (statement["stance"], statement["page"]) == ("refutes", "supports")


def test_a_page_read_as_refuting_under_a_writer_who_supports_splits_the_other_way():
    remember(verdict="refutes", claim=None)
    checks, payload = kept(row("refutes", "supports"))
    statement = sides.statements(checks)[payload.evidence[0]["key"]]
    assert (statement["stance"], statement["page"]) == ("supports", "refutes")


@pytest.mark.parametrize("verdict", ["partly", "unclear", "unread"])
def test_partly_unclear_and_unread_never_split(verdict):
    remember(verdict=verdict)
    checks, _ = kept(row(verdict, "refutes"))
    assert sides.statements(checks) == {}


def test_no_split_when_the_sides_agree_when_there_is_no_reading_or_one_the_site_did_not_make():
    remember()
    assert sides.statements(kept(row("supports", "supports"))[0]) == {}
    assert sides.statements(kept({**CARD, "evidence": [dict(CARD["evidence"][0], check=None)]})[0]) == {}
    check.cache.clear()  # a restart: the card still claims the reading, but this process never made it
    assert sides.statements(kept()[0]) == {}
    assert sides.attach([], None) is None


def test_a_statement_never_takes_the_key_of_linked_evidence_or_of_a_row_on_the_card():
    remember()
    checks, payload = kept(linked=[CLAIM_KEY])
    assert sides.statements(checks)[payload.evidence[0]["key"]]["name"] == f"Statement on {PAGE}"
    checks, _ = kept(linked=[CLAIM_KEY, FALLBACK_KEY])
    assert sides.statements(checks) == {}  # no free name: one piece of evidence on the writer's side, as before


# The write path.

class Transaction:
    def __init__(self):
        self.runs = []

    def run(self, query, **parameters):
        self.runs.append((query, parameters))


COMMON = {"person_key": "acct:ada", "post_id": "p1", "anonymous": False, "now": datetime(2026, 10, 26), "seed": False}


def evidence_runs(tx):
    return [(q, p) for q, p in tx.runs if "Evidence" in q]


def test_the_page_goes_on_its_side_with_its_reading_and_the_statement_on_the_writers_with_answers():
    remember()
    checks, payload = kept()
    tx = Transaction()
    graph_posts.write_payload(tx, payload, COMMON, checks=checks)
    (submit, submit_p), (stance, stance_p), (s_submit, s_submit_p), (s_stance, s_stance_p) = evidence_runs(tx)
    page_key = payload.evidence[0]["key"]
    assert submit == graph_evidence.MERGE_EVIDENCE_SUBMIT_CHECKED and submit_p["url"] == URL and submit_p["source"] == SOURCE
    assert stance == graph_evidence.CREATE_EVIDENCE_STANCE_CHECKED.replace("{label}", "Issue").replace("{rel}", "SUPPORTS")
    assert (stance_p["check"], stance_p["check_quote"], stance_p["answers"]) == ("supports", QUOTE, None)
    statement = checks[page_key]["statement"]
    assert s_submit == graph_evidence.MERGE_EVIDENCE_SUBMIT_CHECKED
    assert (s_submit_p["evidence_key"], s_submit_p["evidence_name"], s_submit_p["url"], s_submit_p["source"]) == (
        statement["key"], statement["name"], None, None)
    assert s_stance == graph_evidence.CREATE_EVIDENCE_STANCE_CHECKED.replace("{label}", "Issue").replace("{rel}", "REFUTES")
    assert s_stance_p["answers"] == page_key and s_stance_p["target_key"] == "climate change"
    assert all(s_stance_p[k] is None for k in ("check", "check_quote", "checked_at", "check_claim", "check_reason",
                                               "personal", "check_quote_at", "check_pasted"))


def test_a_row_that_does_not_split_writes_one_piece_of_evidence_on_the_writers_side():
    remember(verdict="partly")
    checks, payload = kept(row("partly", "refutes"))
    tx = Transaction()
    graph_posts.write_payload(tx, payload, COMMON, checks=checks)
    (_, _), (stance, stance_p) = evidence_runs(tx)
    assert "{rel}" not in stance and ":REFUTES" in stance and stance_p["answers"] is None


def test_flag_off_is_phase_1_byte_for_byte_whatever_the_reading():
    remember()
    _, payload = resolved()
    tx = Transaction()
    graph_posts.write_payload(tx, payload, COMMON)
    (submit, submit_p), (stance, stance_p) = evidence_runs(tx)
    assert submit == graph.MERGE_EVIDENCE_SUBMIT and stance == graph.CREATE_EVIDENCE_STANCE.replace(
        "{label}", "Issue").replace("{rel}", "REFUTES")
    assert "answers" not in stance_p and "answers" not in submit_p


# What this will add.

def test_what_this_will_add_lists_the_page_on_its_side_and_the_statement_on_the_writers():
    remember()
    checks, payload = kept()
    card = CardPayload.model_validate({"issues": [{"name": "Climate change"}],
                                       "evidence": [{"name": PAGE, "url": URL, "stance": "refutes", "about": "Climate change"}]})
    name = checks[payload.evidence[0]["key"]]["statement"]["name"]
    assert sentences(card, "Ada", payload, sides.statements(checks)) == [
        "Ada claims Climate change", f"Ada submits evidence {PAGE}", f"Ada submits evidence {name}",
        f"{PAGE} supports issue of Climate change", f"{name} refutes issue of Climate change"]
    assert sentences(card, "Ada", payload)[-1] == f"{PAGE} refutes issue of Climate change"


@pytest.fixture
def poster(monkeypatch):
    settings = Settings("test passphrase", "test secret", "test admin", "neo4j://localhost:7687", "neo4j", "test",
                        app_env="local", evidence_check_enabled=True, llm_api_key="offline test key")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "attempt_bucket", MinuteBucket(period=3600))
    monkeypatch.setattr(main, "post_spacing", type("Always", (), {"take": lambda self, key: True})())
    monkeypatch.setattr(main.graph, "candidates", lambda: Candidates.empty())
    for name, value in (("list_posts", lambda limit: []), ("post_structure", lambda ids: {}),
                        ("top_issues", lambda limit: [])):
        monkeypatch.setattr(main.graph, name, value)
    seen = []
    monkeypatch.setattr(main.graph, "merge_post", lambda *args, **kwargs: seen.append(kwargs) or "p1")
    client = TestClient(main.app)
    client.post("/enter", data={"passphrase": "test passphrase"})
    yield client, main, seen
    client.close()


def test_the_preview_and_the_post_carry_both_sides_and_the_flag_off_carries_neither(poster, monkeypatch):
    client, main, seen = poster
    remember()
    body = {**CARD, "text": SAID, "display_name": "Ada"}
    said = client.post("/api/preview", json=body).json()["sentences"]
    assert f"{PAGE} supports issue of Climate change" in said
    assert "The rise in CO2 in the air is minuscule and the article proves nothing refutes issue of Climate change" in said
    assert client.post("/api/posts", json=body).status_code == 201
    assert list(sides.statements(seen[-1]["checks"]).values())[0]["page"] == "supports"
    monkeypatch.setattr(main, "settings", replace(main.settings, evidence_check_enabled=False))
    said = client.post("/api/preview", json=body).json()["sentences"]
    assert said[-1] == f"{PAGE} refutes issue of Climate change" and len(said) == 3
    assert client.post("/api/posts", json=body).status_code == 201
    assert seen[-1]["checks"] is None


def test_an_empty_box_posts_both_sentences_as_the_statement(poster, monkeypatch):
    client, main, _ = poster
    texts = []
    monkeypatch.setattr(main.graph, "merge_post", lambda *args, **kwargs: texts.append(args[4]) or "p1")
    remember(claim=None, statement="")
    assert client.post("/api/posts", json={**CARD, "text": "", "display_name": "Ada"}).status_code == 201
    assert f"{PAGE} supports issue of Climate change. Statement on {PAGE} refutes issue of Climate change." in texts[-1]


# Editing: the card shows the page's row on the writer's side again and leaves the statement out.

def test_the_edit_card_folds_the_statement_back_into_the_pages_row():
    page_key, statement_key = PAGE_KEY, FALLBACK_KEY
    rows = [{"rel": "CLAIM", "to_key": "climate change", "to_name": "Climate change", "to_label": "Issue"},
            {"rel": "SUBMIT", "to_key": page_key, "to_name": PAGE, "to_label": "Evidence"},
            {"rel": "SUBMIT", "to_key": statement_key, "to_name": f"Statement on {PAGE}", "to_label": "Evidence"},
            {"rel": "SUPPORTS", "from_label": "Evidence", "from_key": page_key, "from_name": PAGE,
             "to_key": "climate change", "to_name": "Climate change", "to_label": "Issue"},
            {"rel": "REFUTES", "from_label": "Evidence", "from_key": statement_key, "from_name": f"Statement on {PAGE}",
             "to_key": "climate change", "to_name": "Climate change", "to_label": "Issue"}]
    stored = json.dumps({"evidence": [{"key": page_key, "url": URL}]})
    checks = {(page_key, "climate change"): {"check": "supports", "check_quote": QUOTE, "url": URL}}
    statements = [{"evidence_key": statement_key, "answers": page_key, "target_key": "climate change", "stance": "REFUTES"}]
    card = edit_card(rows, stored, {}, checks, statements)
    assert [(e["name"], e["stance"], e["check"]["verdict"]) for e in card["evidence"]] == [(PAGE, "refutes", "supports")]
    # Without the switch the edges are shown as they are: two plain rows.
    assert [(e["name"], e["stance"]) for e in edit_card(rows, stored, {})["evidence"]] == [
        (PAGE, "supports"), (f"Statement on {PAGE}", "refutes")]


def test_the_edit_preview_lists_both_sides_from_the_reading_the_post_holds(poster, monkeypatch):
    from app import routes_own_posts
    from app.members import Member
    _, main, _ = poster
    stored = {(PAGE_KEY, "climate change"): {"url": URL, "check": "supports", "check_quote": QUOTE,
                                             "check_claim": None, "checked_at": None}}
    monkeypatch.setattr(routes_own_posts, "stored_checks", lambda post_id, payload: stored)
    data = main.PostRequest.model_validate({**CARD, "text": SAID})
    payload = resolve_payload(data, Candidates.empty())
    card = CardPayload.model_validate({"issues": [{"name": "Climate change"}],
                                       "evidence": [{"name": PAGE, "url": URL, "stance": "refutes", "about": "Climate change"}]})
    ada = Member(key="acct:ada", name="Ada", email="ada@example.org", admin=False)
    shown = routes_own_posts.edit_preview(ada, {"id": "p1", "payload": "{}", "anonymous": False}, data, payload, card)
    assert shown["sentences"][-2:] == [f"{PAGE} supports issue of Climate change",
                                       f"Statement on {PAGE} refutes issue of Climate change"]


def test_an_edit_rebuilds_the_same_statement_from_the_reading_the_post_holds():
    sent, payload = resolved()
    stored = {(payload.evidence[0]["key"], "climate change"): {"url": URL, "check": "supports", "check_quote": QUOTE,
                                                               "check_claim": CLAIM, "checked_at": None}}
    checks = sides.attach(payload.evidence, kept_checks(sent.evidence, payload.evidence, SAID, stored))
    first = sides.statements(checks)[payload.evidence[0]["key"]]
    again = sides.statements(sides.attach(payload.evidence, kept_checks(sent.evidence, payload.evidence, SAID, stored)))
    assert again[payload.evidence[0]["key"]] == first and first["name"].startswith("The rise in CO2")


# Source confidence and Ask the record: the statement is not a source and is never counted as one.

def q39(evidence_key, stance, check=None, answers=None, **extra):
    return {"target_kind": "issue", "target_key": "climate change", "evidence_key": evidence_key, "stance": stance,
            "check": check, "check_quote": QUOTE if check else None, "answers": answers, "source_known": bool(check),
            "source_type": "reference" if check else None, "source_primary": False if check else None,
            "source_published": "2026-10" if check else None, **extra}


def test_source_confidence_never_counts_the_statement_and_says_whose_words_it_is():
    rows = [q39("page", "SUPPORTS", "supports"), q39("own words", "REFUTES", answers="page"), q39("nasa", "SUPPORTS")]
    lines = confidence.lines(rows, today=date(2026, 10, 26))
    page = lines[("issue", "climate change", "page", "SUPPORTS")]
    assert page["words"] == "A reference work from October 2026. Secondary source. One other piece of evidence here says the same."
    assert page["differs"] is None
    assert lines[("issue", "climate change", "nasa", "SUPPORTS")]["words"] == "One other piece of evidence here says the same."
    assert lines[("issue", "climate change", "own words", "REFUTES")]["answers"] == "page"
    evidence = [{"key": "page", "name": PAGE, "url": URL, "stance": "SUPPORTS"},
                {"key": "own words", "name": "Own words", "url": None, "stance": "REFUTES"}]
    confidence.annotate("climate change", evidence, [], rows, today=date(2026, 10, 26))
    assert evidence[1]["source_note"] == f"The writer's own words about {PAGE}, which was read as agreeing with this."
    assert evidence[1]["confidence"] is None and evidence[0]["source_note"] is None


def test_the_ask_digest_marks_the_statement_as_the_writers_own_words_beside_the_page():
    def edge(key, url, stance, check=None, answers=None):
        return {"key": key, "name": key.title(), "url": url, "source_known": bool(check), "source_type": "reference",
                "source_primary": False, "source_published": "2026-10", "source_cites": True,
                "target_kind": "issue", "target_key": "climate change", "target_name": "Climate change",
                "target_url": None, "stance": stance, "check": check, "personal": None, "post_id": None,
                "created_at": datetime(2026, 10, 26, tzinfo=timezone.utc), "answers": answers}
    issue = {"key": "climate change", "name": "Climate change", "people": 1, "claims": 1}
    rows = [edge("page", URL, "supports", "supports"), edge("own words", None, "refutes", answers="page")]
    digest = json.loads(ask.build("Climate change", [issue], [], rows, [], today=date(2026, 10, 26)).text)
    page, own = digest["evidence"]
    assert page["link"] == URL and "source" in page and "writers_own_words_beside" not in page
    assert own == {"id": "E2", "name": "Own Words", "writers_own_words_beside": "E1",
                   "about": [{"what": "issue Climate change", "side": "refutes"}]}
    assert digest["evidence_backed_by_other_evidence"] == 0


def test_a_copy_holds_answers_as_text_only():
    assert backup.properties({"answers": "page"}) == {"answers": "page"}
    with pytest.raises(backup.InvalidBackup):
        backup.properties({"answers": True})
