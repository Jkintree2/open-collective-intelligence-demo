"""Phase 2's write path: a row keeps its reading only when the site made it, and with the flag off the
evidence statements and their parameters are exactly Phase 1's. No network, no database."""

import importlib
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import check, graph, graph_evidence, graph_posts
from app.auth import MinuteBucket
from app.check import NO_CHECK, Check, kept_checks
from app.config import Settings
from app.extract import Candidates, CardPayload, resolve_payload

URL = "https://news.example.org/story"
QUOTE = "A survey of forty coastal towns found flooding days doubled since 2000."
SOURCE = {"type": "news", "primary": False, "published": "2024-03"}
READ_AT = "2026-10-20T12:00:00+00:00"
CARD = {"issues": [{"name": "Coastal flooding"}],
        "evidence": [{"name": "Forty town survey", "url": URL, "stance": "supports", "about": "Coastal flooding",
                      "check": {"verdict": "supports", "quote": QUOTE}}]}


@pytest.fixture(autouse=True)
def empty_cache():
    check.cache.clear()
    yield
    check.cache.clear()


def remember(verdict="supports", quote=QUOTE, statement="Floods are worse.", about="Coastal flooding"):
    reading = Check(verdict, URL, quote=quote, source=SOURCE if verdict != "unread" else None, checked_at=READ_AT)
    check.cache.put(check.cache_key(URL, about, statement), reading)
    return reading


def resolved(card=CARD):
    card = CardPayload.model_validate(card)
    return card, resolve_payload(card, Candidates.empty())


def test_the_card_row_carries_a_check_and_junk_becomes_none():
    assert CardPayload.model_validate(CARD).evidence[0].check == {"verdict": "supports", "quote": QUOTE}
    for junk in ("supports", ["supports"], {"quote": QUOTE}, {"verdict": 3}):
        row = dict(CARD["evidence"][0], check=junk)
        assert CardPayload.model_validate({"evidence": [row]}).evidence[0].check is None


def test_a_reading_the_site_made_is_kept_with_its_source_facts():
    remember()
    card, payload = resolved()
    kept = kept_checks(card.evidence, payload.evidence, "Floods are worse.")
    assert kept == {"forty town survey": {"check": "supports", "check_quote": QUOTE, "source": SOURCE,
                                          "checked_at": datetime(2026, 10, 20, 12, tzinfo=timezone.utc),
                                          "check_claim": None, "check_reason": None,
                                          "check_quote_at": None, "check_pasted": None}}


def test_a_reading_the_site_never_made_is_stored_as_none():
    remember(verdict="refutes")
    card, payload = resolved()
    assert kept_checks(card.evidence, payload.evidence, "Floods are worse.") == {"forty town survey": NO_CHECK}
    check.cache.clear()
    assert kept_checks(card.evidence, payload.evidence, "Floods are worse.") == {"forty town survey": NO_CHECK}


def test_a_row_without_a_link_or_a_claimed_check_has_none():
    remember()
    no_link = {**CARD, "evidence": [dict(CARD["evidence"][0], url=None)]}
    card, payload = resolved(no_link)
    assert kept_checks(card.evidence, payload.evidence, "Floods are worse.") == {"forty town survey": NO_CHECK}
    unclaimed = {**CARD, "evidence": [dict(CARD["evidence"][0], check=None)]}
    card, payload = resolved(unclaimed)
    assert kept_checks(card.evidence, payload.evidence, "Floods are worse.") == {"forty town survey": NO_CHECK}


def test_an_unread_page_is_kept_without_source_facts():
    remember(verdict="unread", quote=None)
    row = dict(CARD["evidence"][0], check={"verdict": "unread", "quote": None})
    card, payload = resolved({**CARD, "evidence": [row]})
    kept = kept_checks(card.evidence, payload.evidence, "Floods are worse.")["forty town survey"]
    assert kept["check"] == "unread" and kept["source"] is None


def test_an_edit_keeps_the_reading_the_post_already_holds():
    card, payload = resolved()
    then = datetime(2026, 10, 1, tzinfo=timezone.utc)
    stored = {("forty town survey", "coastal flooding"): {"url": URL, "check": "supports", "check_quote": QUOTE,
                                                          "checked_at": then}}
    kept = kept_checks(card.evidence, payload.evidence, "Reworded.", stored)["forty town survey"]
    assert kept == {"check": "supports", "check_quote": QUOTE, "checked_at": then, "source": None,
                    "check_claim": None, "check_reason": None, "check_quote_at": None, "check_pasted": None}
    moved = {key: dict(value, url="https://elsewhere.example.org/") for key, value in stored.items()}
    assert kept_checks(card.evidence, payload.evidence, "Reworded.", moved)["forty town survey"] == NO_CHECK
    other = {key: dict(value, check="refutes") for key, value in stored.items()}
    assert kept_checks(card.evidence, payload.evidence, "Reworded.", other)["forty town survey"] == NO_CHECK


class Transaction:
    def __init__(self):
        self.runs = []

    def run(self, query, **parameters):
        self.runs.append((query, parameters))


COMMON = {"person_key": "anon:x", "post_id": "p1", "anonymous": False, "now": datetime(2026, 10, 20), "seed": False}


def evidence_runs(tx):
    return [(q, p) for q, p in tx.runs if "Evidence" in q]


def test_flag_off_writes_evidence_exactly_as_phase_1():
    _, payload = resolved()
    tx = Transaction()
    graph_posts.write_payload(tx, payload, COMMON)
    (submit, submit_params), (stance, stance_params) = evidence_runs(tx)
    assert submit == graph.MERGE_EVIDENCE_SUBMIT
    assert submit_params == {"evidence_key": "forty town survey", "evidence_name": "Forty town survey", "url": URL, **COMMON}
    assert stance == graph.CREATE_EVIDENCE_STANCE.replace("{label}", "Issue").replace("{rel}", "SUPPORTS")
    assert stance_params == {"evidence_key": "forty town survey", "target_key": "coastal flooding", **COMMON}


def test_flag_on_writes_the_reading_on_the_edge_and_the_source_once():
    _, payload = resolved()
    tx = Transaction()
    kept = {"forty town survey": {"check": "supports", "check_quote": QUOTE, "checked_at": COMMON["now"],
                                  "source": SOURCE}}
    graph_posts.write_payload(tx, payload, COMMON, checks=kept)
    (submit, submit_params), (stance, stance_params) = evidence_runs(tx)
    assert submit == graph_evidence.MERGE_EVIDENCE_SUBMIT_CHECKED and submit_params["source"] == SOURCE
    assert "e.source_checked_at IS NULL" in submit and "e.url = $url" in submit
    assert stance == graph_evidence.CREATE_EVIDENCE_STANCE_CHECKED.replace("{label}", "Issue").replace("{rel}", "SUPPORTS")
    assert (stance_params["check"], stance_params["check_quote"], stance_params["checked_at"]) == ("supports", QUOTE, COMMON["now"])


def test_flag_on_without_a_kept_reading_writes_nulls():
    _, payload = resolved()
    tx = Transaction()
    graph_posts.write_payload(tx, payload, COMMON, checks={})
    (_, submit_params), (_, stance_params) = evidence_runs(tx)
    assert submit_params["source"] is None
    assert (stance_params["check"], stance_params["check_quote"], stance_params["checked_at"]) == (None, None, None)


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


def test_posting_with_the_flag_on_keeps_only_a_reading_the_site_made(poster):
    client, _, seen = poster
    remember(statement="Floods are worse.")
    body = {**CARD, "text": "Floods are worse.", "name": "Ada"}
    assert client.post("/api/posts", json=body).status_code == 201
    assert seen[-1]["checks"]["forty town survey"]["check"] == "supports"
    forged = {**body, "evidence": [dict(CARD["evidence"][0], check={"verdict": "refutes", "quote": QUOTE})]}
    assert client.post("/api/posts", json=forged).status_code == 201
    assert seen[-1]["checks"] == {"forty town survey": NO_CHECK}


def test_posting_with_the_flag_off_passes_no_checks(poster, monkeypatch):
    client, main, seen = poster
    monkeypatch.setattr(main, "settings", replace(main.settings, evidence_check_enabled=False))
    remember(statement="Floods are worse.")
    assert client.post("/api/posts", json={**CARD, "text": "Floods are worse.", "name": "Ada"}).status_code == 201
    assert seen[-1]["checks"] is None


def test_a_reading_for_another_claim_is_not_kept_when_the_row_falls_back_to_the_first_issue():
    # The row's "about" names nothing on the card or in the record, so the evidence lands on the
    # card's first issue; the reading was of a different claim and must not go with it.
    remember(about="Something the page plainly says")
    stray = {**CARD, "evidence": [dict(CARD["evidence"][0], about="Something the page plainly says")]}
    card, payload = resolved(stray)
    assert payload.evidence[0]["target_key"] == "coastal flooding"
    assert kept_checks(card.evidence, payload.evidence, "Floods are worse.") == {"forty town survey": NO_CHECK}


def test_a_second_row_with_the_same_name_cannot_lend_its_reading_to_the_first():
    remember(about="Rising sea levels")
    first = dict(CARD["evidence"][0], check=None)
    second = dict(CARD["evidence"][0], about="Rising sea levels")
    card, payload = resolved({"issues": [{"name": "Coastal flooding"}, {"name": "Rising sea levels"}],
                              "evidence": [first, second]})
    assert [row["target_key"] for row in payload.evidence] == ["coastal flooding"]
    assert kept_checks(card.evidence, payload.evidence, "Floods are worse.") == {"forty town survey": NO_CHECK}


# Revision round (03_schema.md, "Revision round: agrees, partly agrees, contradicts; ...").
def test_a_kept_reading_carries_the_writers_sentence_only_while_the_statement_holds_it():
    claim = "The survey found flooding days tripled since 2000."
    statement = f"Floods are worse. {claim}"
    reading = Check("partly", URL, quote=QUOTE, reason="The page says doubled, not tripled.", claim=claim,
                    source=SOURCE, checked_at=READ_AT)
    check.cache.put(check.cache_key(URL, "Coastal flooding", statement), reading)
    row = dict(CARD["evidence"][0], check={"verdict": "partly", "quote": QUOTE})
    card, payload = resolved({**CARD, "evidence": [row]})
    kept = kept_checks(card.evidence, payload.evidence, statement)["forty town survey"]
    assert (kept["check"], kept["check_claim"], kept["check_reason"]) == ("partly", claim, "The page says doubled, not tripled.")
    # Tidied afterwards so the sentence is gone: the reading stays, the sentence does not.
    tidied = kept_checks(card.evidence, payload.evidence, "Floods are worse, a survey says.")["forty town survey"]
    assert (tidied["check"], tidied["check_claim"]) == ("partly", None)


def test_personal_experience_is_kept_only_on_a_row_with_no_link():
    rows = [{"name": "What I saw", "url": None, "personal": True, "about": "Coastal flooding"},
            {"name": "A report", "url": URL, "personal": True, "about": "Coastal flooding"},
            {"name": "What I heard", "url": None, "personal": "yes", "about": "Coastal flooding"}]
    _, payload = resolved({"issues": [{"name": "Coastal flooding"}], "evidence": rows})
    assert [row.get("personal") for row in payload.evidence] == [True, None, None]
    tx = Transaction()
    graph_posts.write_payload(tx, payload, COMMON, checks={})
    stances = [params for query, params in evidence_runs(tx) if "CREATE (e)" in query]
    assert [params["personal"] for params in stances] == [True, None, None]
    assert "personal: $personal" in graph_evidence.CREATE_EVIDENCE_STANCE_CHECKED
    # With the flag off nothing of it is written: statement 5b is Phase 1's.
    tx = Transaction()
    graph_posts.write_payload(tx, payload, COMMON)
    assert all("personal" not in params for _, params in evidence_runs(tx))


def test_the_edge_takes_the_writers_sentence_and_the_reason():
    _, payload = resolved()
    tx = Transaction()
    kept = {"forty town survey": {"check": "partly", "check_quote": QUOTE, "checked_at": COMMON["now"],
                                  "source": {**SOURCE, "cites": True}, "check_claim": "Flooding tripled.",
                                  "check_reason": "The page says doubled."}}
    graph_posts.write_payload(tx, payload, COMMON, checks=kept)
    (submit, submit_params), (stance, stance_params) = evidence_runs(tx)
    assert "e.source_cites = $source.cites" in submit and submit_params["source"]["cites"] is True
    assert (stance_params["check_claim"], stance_params["check_reason"]) == ("Flooding tripled.", "The page says doubled.")
