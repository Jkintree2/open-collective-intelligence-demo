"""v0.3: Home tells a statement from a question by rules, and says it is unsure when it can't (decision D2). No
model call, no database. The cases in kind_cases.json come from the Ask fixture's questions, the seed posts and
John's emails; John, 4 November: the final period or question mark is not always there."""

import json
from pathlib import Path

import pytest

from app import graph_questions
from app.home import QUESTION_OPENERS, kind_of

CASES = json.loads((Path(__file__).resolve().parent / "kind_cases.json").read_text(encoding="utf-8"))
HOMELESSNESS = (
    "Why do we tolerate homelessness in St. Louis? Because we have decided that housing is something people earn "
    "rather than something they are owed. The city spends millions each year on emergency rooms, police calls and "
    "jail beds for people who sleep outside, and almost nothing on the apartments that would end the problem. "
    "Housing first programs in Houston and in Finland show that giving people a home before asking them to fix "
    "everything else costs less and works better. Houston cut its homeless count by more than half in ten years by "
    "moving people straight into apartments with support. Finland is the only country in Europe where homelessness "
    "keeps falling, because it bought and built small flats and gave them to people with no conditions. St. Louis "
    "has empty buildings downtown and federal money it has not spent. We should turn those buildings into homes, "
    "pay for caseworkers instead of more police overtime, and count every person who moves inside. The Universal "
    "Declaration of Human Rights says in Article 25 that everyone has the right to housing, and our city signed on "
    "to human rights principles years ago. It is time we acted like it. A city that can find money for a new "
    "stadium can find money to house the few thousand people who sleep on its streets every night of the year, "
    "and it would save money doing it. Nobody chooses to sleep in a doorway in January. Most people on our streets "
    "lost a job, a partner or their health, and then lost the lease that held everything else together. Every "
    "winter we read about someone who froze to death a few blocks from city hall, and every spring we forget. We can "
    "do better than that, and we should start this year. Housing is the cure."
)


def test_there_are_enough_cases_of_each_kind():
    kinds = [case["kind"] for case in CASES]
    assert len(CASES) >= 40
    assert {kind: kinds.count(kind) >= 5 for kind in ("statement", "question", "unsure")} == {
        "statement": True, "question": True, "unsure": True}


@pytest.mark.parametrize("case", CASES, ids=[case["text"][:40] or "empty" for case in CASES])
def test_cases(case):
    assert kind_of(case["text"]) == case["kind"], case.get("why", "")


def test_long_statement_with_a_question_is_not_a_question():
    """Review Focus 1: a long statement that opens with a question must not go to Ask, which caps questions at 500
    characters."""
    assert len(HOMELESSNESS.split()) > 250
    assert kind_of(HOMELESSNESS) == "statement"


def test_over_question_max_never_question():
    """Review Focus 2: a question over 500 characters is never cut silently; it is unsure, so the writer chooses."""
    long_question = "How does " + "the veto and " * 60 + "homelessness relate to the UDHR?"
    assert len(long_question) > graph_questions.QUESTION_MAX
    assert kind_of(long_question) == "unsure"
    assert kind_of(long_question.rstrip("?")) == "statement"
    at_the_cap = "What " + "x" * (graph_questions.QUESTION_MAX - 6) + "?"
    assert len(at_the_cap) == graph_questions.QUESTION_MAX
    assert kind_of(at_the_cap) == "question"


@pytest.mark.parametrize("text", ["Tell me more", "Tell me more.", "Why?", "why", "More", "more", "More.",
                                  "And why?", "go on", "What else?"])
def test_follow_ups_are_questions(text):
    assert kind_of(text) == "question"


def test_openers_include_the_planned_words():
    assert {"how", "what", "why", "who", "where", "when", "which", "is", "are", "does", "do", "can", "should",
            "could", "would", "will", "tell", "explain", "summarize", "list", "show"} <= QUESTION_OPENERS


def test_a_question_mark_inside_a_link_is_not_a_question():
    assert kind_of("Rents rose by a fifth https://example.org/report?year=2026 and wages did not") == "statement"


def test_capitals_and_spacing_do_not_matter():
    assert kind_of("  HOW DOES HOMELESSNESS RELATE TO THE UDHR  ") == "question"
    assert kind_of("Is housing\na human right") == "question"
