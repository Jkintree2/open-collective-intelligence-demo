"""The back room's list of readings changed by their writers (app/readings.py); no database."""

import json
from datetime import datetime, timezone

from app import readings
from app.extract import CardPayload, prepared_card, resolve_payload
from app.payload import Candidates
from app.text import make_key

VETO, ABOLISH = "Security Council veto", "Limit or abolish the Security Council veto"
RECORD = Candidates(issues={make_key(VETO): {"name": VETO, "parent_key": None}},
                    solutions={make_key(ABOLISH): ABOLISH}, solution_issues={make_key(ABOLISH): [VETO]})
TEXT = "I oppose the Security Council veto because it has blocked action on Syria."
WHEN = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)


def resolved(card: dict) -> str:
    return resolve_payload(CardPayload.model_validate({"found": True, **card}), RECORD).as_json()


def row(reading, posted, **fields):
    return {"id": "p1", "text": TEXT, "display_name": "Ada", "created_at": WHEN, "edited_at": None,
            "payload": posted, "extraction_raw": "{}", "reading_payload": reading, **fields}


OPPOSES = resolved({"solutions": [{"name": ABOLISH, "for_issue": VETO, "stance": "oppose"}]})
APPROVES = resolved({"solutions": [{"name": ABOLISH, "for_issue": VETO, "stance": "approve"}]})


def test_a_stance_turned_is_taken_out_and_added():
    [shown], unreadable = readings.page_rows([row(OPPOSES, APPROVES)], RECORD)
    assert shown["taken_out"] == [f"opposes {ABOLISH}"] and shown["added"] == [f"approves {ABOLISH}"]
    assert shown["name"] == "Ada" and shown["when"] == "2 November 2026" and not shown["worked_out_today"]
    assert unreadable == 0


def test_an_unchanged_reading_is_not_listed():
    assert readings.page_rows([row(OPPOSES, OPPOSES)], RECORD) == ([], 0)


def test_an_emptied_card_lists_everything_as_taken_out():
    reading = resolved({"issues": [{"name": VETO}], "evidence": [
        {"name": "Veto blocked action on Syria", "stance": "supports", "about": VETO}]})
    [shown], _ = readings.page_rows([row(reading, resolved({}))], RECORD)
    assert shown["added"] == []
    assert shown["taken_out"] == [f"claims {VETO}",
                                  f"submits evidence Veto blocked action on Syria, which supports issue of {VETO}"]


def test_a_new_solution_names_its_issue_and_a_link_is_shown():
    posted = resolved({"solutions": [{"name": "Regional security councils", "for_issue": VETO, "stance": "none"}],
                       "evidence": [{"name": "Vetoes since 1946", "url": "https://example.org/vetoes",
                                     "stance": "supports", "about": VETO}]})
    [shown], _ = readings.page_rows([row(resolved({}), posted)], RECORD)
    assert shown["added"] == [f"proposes solution Regional security councils for {VETO}",
                              f"submits evidence Vetoes since 1946 (https://example.org/vetoes), which supports issue of {VETO}"]


def test_an_anonymous_post_reads_anonymous():
    [shown], _ = readings.page_rows([row(OPPOSES, APPROVES, display_name=None)], RECORD)
    assert shown["name"] == "Anonymous"


def test_an_unreadable_reading_is_counted_not_listed():
    older = row(None, APPROVES, extraction_raw="not a reading")
    assert readings.page_rows([older], RECORD) == ([], 1)


def test_an_older_post_is_worked_out_today():
    raw = json.dumps({"found": True, "issues": [], "evidence": [],
                      "solutions": [{"name": ABOLISH, "for_issue": VETO, "stance": "approve"}]})
    older = row(None, OPPOSES, extraction_raw=raw, text="We should abolish the Security Council veto.")
    [shown], _ = readings.page_rows([older], RECORD)
    assert shown["worked_out_today"] and shown["taken_out"] == [f"approves {ABOLISH}"]


def test_the_latest_change_dates_an_edited_post():
    [shown], _ = readings.page_rows([row(OPPOSES, APPROVES, edited_at=datetime(2026, 11, 3, tzinfo=timezone.utc))],
                                    RECORD)
    assert shown["when"] == "3 November 2026"


def test_reading_payload_resolves_the_reading_as_a_post_is_resolved():
    raw = json.dumps({"found": True, "issues": [{"name": VETO}], "solutions": [], "evidence": [
        {"name": "Veto blocked action on Syria", "url": "https://example.org/made-up", "stance": "supports",
         "about": VETO}]})
    card = prepared_card(CardPayload.model_validate(json.loads(raw)), RECORD, TEXT)
    assert readings.reading_payload(raw, RECORD, TEXT) == resolve_payload(card, RECORD).as_json()
    assert json.loads(readings.reading_payload(raw, RECORD, TEXT))["evidence"][0]["url"] is None  # not in the text
    assert readings.reading_payload(None, RECORD, TEXT) is None
    assert readings.reading_payload("no reading here", RECORD, TEXT) is None
    assert readings.reading_payload(raw, RECORD, TEXT, resolve=lambda card: resolve_payload(card, Candidates())) \
        == resolve_payload(card, Candidates()).as_json()
