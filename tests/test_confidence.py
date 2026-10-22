"""Source confidence on the issue page (04_interface.md, "Source confidence, on the issue page";
03_schema.md, Q39 and the disagreement rule). Offline: no network, no database."""

from datetime import date

import pytest

from app import confidence
from app.check import more_than_five_years, source_words

TODAY = date(2026, 10, 21)


@pytest.mark.parametrize("published,old", [
    ("2021-10-20", True),     # five years and a day
    ("2021-10-21", False),    # exactly five years
    ("2021-10", False),       # counts from 31 October 2021
    ("2021-09", True),        # counts from 30 September 2021
    ("2020", True),           # counts from 31 December 2020
    ("2021", False),          # counts from 31 December 2021
    ("2026-01-01", False),
    (None, False),
    ("not a date", False),
])
def test_more_than_five_years_counts_from_the_end_of_what_is_given(published, old):
    assert more_than_five_years(published, TODAY) is old


def test_a_leap_day_five_years_on_is_the_last_day_of_february():
    assert more_than_five_years("2023-02-27", date(2028, 2, 29)) is True
    assert more_than_five_years("2023-02-28", date(2028, 2, 29)) is False


@pytest.mark.parametrize("source,words", [
    ({"type": "news", "primary": False, "published": "2018-03-02"},
     "A news report from March 2018. More than five years old. Secondary source."),
    ({"type": "news", "primary": False, "published": "2024-03-14"}, "A news report from March 2024. Secondary source."),
    ({"type": "research", "primary": True, "published": "2015"},
     "A research paper from 2015. More than five years old. Primary source."),
    ({"type": "government", "primary": None, "published": None}, "A government source. Date not given."),
])
def test_source_words_say_the_age(source, words):
    assert source_words(source, today=TODAY) == words


@pytest.mark.parametrize("same,other,words", [
    (0, 0, None),
    (1, 0, "One other piece of evidence here says the same."),
    (2, 0, "Two other pieces of evidence here say the same."),
    (0, 1, "One other piece of evidence here disagrees."),
    (0, 2, "Two other pieces of evidence here disagree."),
    (1, 2, "One other piece of evidence here says the same; two disagree."),
    (2, 1, "Two other pieces of evidence here say the same; one disagrees."),
    (12, 0, "12 other pieces of evidence here say the same."),
    (10, 11, "Ten other pieces of evidence here say the same; 11 disagree."),
])
def test_agreement_words(same, other, words):
    assert confidence.agreement_words(same, other) == words


def row(target, evidence, stance, check=None, kind="solution", facts=None):
    facts = facts or {}
    return {"target_kind": kind, "target_key": target, "evidence_key": evidence, "stance": stance, "check": check,
            "source_known": bool(facts), "source_type": facts.get("type"),
            "source_primary": facts.get("primary"), "source_published": facts.get("published")}


NEWS = {"type": "news", "primary": False, "published": "2024-03-14"}


def test_lines_count_agreement_on_the_same_target_only():
    rows = [row("veto", "a", "SUPPORTS", "supports", facts=NEWS), row("veto", "b", "SUPPORTS"),
            row("veto", "c", "REFUTES"), row("other", "d", "SUPPORTS"), row("veto", "x", "SUPPORTS", kind="issue")]
    lines = confidence.lines(rows, today=TODAY)
    assert lines[("solution", "veto", "a", "SUPPORTS")] == {
        "words": "A news report from March 2024. Secondary source. "
                 "One other piece of evidence here says the same; one disagrees.",
        "differs": None, "readings": [], "personal": False}
    assert lines[("solution", "veto", "c", "REFUTES")]["words"] == "Two other pieces of evidence here disagree."
    assert lines[("solution", "other", "d", "SUPPORTS")] is None
    assert lines[("issue", "veto", "x", "SUPPORTS")] is None


def test_an_item_cited_by_several_posts_counts_once_and_never_itself():
    rows = [row("veto", "a", "SUPPORTS"), row("veto", "a", "SUPPORTS"), row("veto", "b", "SUPPORTS"),
            row("veto", "b", "SUPPORTS")]
    assert confidence.lines(rows, today=TODAY)[("solution", "veto", "a", "SUPPORTS")]["words"] == \
        "One other piece of evidence here says the same."


def test_an_item_on_both_sides_counts_once_on_each():
    rows = [row("veto", "a", "SUPPORTS"), row("veto", "a", "REFUTES"), row("veto", "b", "SUPPORTS")]
    lines = confidence.lines(rows, today=TODAY)
    assert lines[("solution", "veto", "b", "SUPPORTS")]["words"] == \
        "One other piece of evidence here says the same; one disagrees."
    assert lines[("solution", "veto", "a", "SUPPORTS")]["words"] == "One other piece of evidence here says the same."
    assert lines[("solution", "veto", "a", "REFUTES")]["words"] == "One other piece of evidence here disagrees."


@pytest.mark.parametrize("stance,checks,differs", [
    ("SUPPORTS", ["refutes"], "The page was read as contradicting this."),
    ("SUPPORTS", ["supports", "refutes", None], "The page was read as contradicting this."),
    ("REFUTES", ["supports"], "The page was read as agreeing with this."),
    ("REFUTES", ["partly"], "The page was read as partly agreeing with this."),
    ("REFUTES", ["partly", "supports"], "The page was read as agreeing with this."),
    ("SUPPORTS", ["partly"], None),
    ("SUPPORTS", ["supports", "unclear", "unread", None], None),
    ("REFUTES", ["refutes"], None),
])
def test_the_disagreement_line_shows_when_any_reading_went_the_other_way(stance, checks, differs):
    rows = [row("veto", "a", stance, check) for check in checks]
    assert (confidence.lines(rows, today=TODAY)[("solution", "veto", "a", stance)] or {}).get("differs") == differs


def test_a_reading_on_another_target_does_not_flag_this_one():
    rows = [row("veto", "a", "SUPPORTS", "refutes", kind="issue"), row("veto", "a", "SUPPORTS", "supports")]
    lines = confidence.lines(rows, today=TODAY)
    assert lines[("solution", "veto", "a", "SUPPORTS")] is None
    assert lines[("issue", "veto", "a", "SUPPORTS")]["differs"] == "The page was read as contradicting this."


def test_annotate_puts_the_lines_on_the_page_items():
    rows = [row("veto", "a", "SUPPORTS", "refutes", kind="issue", facts=NEWS), row("abolish", "b", "REFUTES")]
    evidence = [{"key": "a", "name": "A", "url": None, "stance": "SUPPORTS"}]
    solutions = [{"key": "abolish", "evidence": [{"key": "b", "name": "B", "url": None, "stance": "REFUTES"}]}]
    confidence.annotate("veto", evidence, solutions, rows, today=TODAY)
    assert evidence[0]["confidence"] == "A news report from March 2024. Secondary source."
    assert evidence[0]["differs"] == "The page was read as contradicting this."
    assert solutions[0]["evidence"][0]["confidence"] is None and solutions[0]["evidence"][0]["differs"] is None


def test_the_words_are_in_the_interface_doc():
    from pathlib import Path
    doc = (Path(__file__).resolve().parent.parent / "docs/planning/04_interface.md").read_text(encoding="utf-8")
    for line in (confidence.AGAINST, confidence.FOR, "More than five years old.",
                 confidence.agreement_words(1, 0), confidence.agreement_words(2, 0),
                 confidence.agreement_words(0, 1), confidence.agreement_words(0, 2),
                 confidence.agreement_words(1, 2), confidence.agreement_words(2, 1)):
        assert line in doc


# Revision round (03_schema.md and 04_interface.md, "Revision round: agrees, partly agrees, contradicts").
def reading_row(check, quote="Flooding days doubled.", claim=None, reason=None, personal=None, stance="SUPPORTS"):
    return {**row("veto", "a", stance, check, kind="issue"), "check_quote": quote, "check_claim": claim,
            "check_reason": reason, "personal": personal}


def test_each_distinct_reading_with_a_quote_is_shown_once_in_johns_words():
    rows = [reading_row("partly", claim="Flooding days tripled.", reason="The page says doubled, not tripled."),
            reading_row("partly", claim="Flooding days tripled.", reason="The page says doubled, not tripled."),
            reading_row("supports", reason="Not shown for agrees."), reading_row("refutes", claim="Floods are rare."),
            reading_row("unclear", quote=None), reading_row("unread", quote=None), reading_row("supports", quote=None)]
    found = confidence.lines(rows, today=TODAY)[("issue", "veto", "a", "SUPPORTS")]
    assert found["readings"] == [
        {"word": "Partly agrees", "claim": "Flooding days tripled.", "quote": "Flooding days doubled.",
         "said": "The page says", "pasted": None, "reason": "The page says doubled, not tripled."},
        {"word": "Agrees", "claim": None, "quote": "Flooding days doubled.", "said": "The page says", "pasted": None,
         "reason": None},
        {"word": "Contradicts", "claim": "Floods are rare.", "quote": "Flooding days doubled.",
         "said": "The page says", "pasted": None, "reason": None}]


def test_evidence_with_no_link_says_so_or_personal_experience():
    rows = [{**row("veto", "seen", "SUPPORTS", kind="issue"), "personal": True},
            row("veto", "told", "SUPPORTS", kind="issue")]
    evidence = [{"key": "seen", "name": "What I saw", "url": None, "stance": "SUPPORTS"},
                {"key": "told", "name": "What I heard", "url": None, "stance": "SUPPORTS"},
                {"key": "linked", "name": "A report", "url": "https://example.org/r", "stance": "SUPPORTS"}]
    confidence.annotate("veto", evidence, [], rows, today=TODAY)
    assert [item["source_note"] for item in evidence] == ["From personal experience.", "No source given.", None]


def test_names_its_sources_follows_primary_or_secondary():
    assert source_words({**NEWS, "cites": True}, today=TODAY) == \
        "A news report from March 2024. Secondary source. Names its sources."
    assert source_words({**NEWS, "cites": False}, today=TODAY) == "A news report from March 2024. Secondary source."
    facts = {**row("veto", "a", "SUPPORTS", kind="issue", facts=NEWS), "source_cites": True}
    assert confidence.lines([facts], today=TODAY)[("issue", "veto", "a", "SUPPORTS")]["words"].endswith("Names its sources.")


def test_the_revision_round_words_are_in_the_interface_doc():
    from pathlib import Path
    doc = (Path(__file__).resolve().parent.parent / "docs/planning/04_interface.md").read_text(encoding="utf-8")
    for line in (confidence.PARTLY_FOR, confidence.NO_SOURCE, confidence.PERSONAL, "Names its sources.",
                 "From my own experience", "The statement says:", "The page says:", "You wrote:",
                 *confidence.WORDS.values()):
        assert line in doc, line
