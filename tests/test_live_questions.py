"""Phase 3, the questions people asked (Q47 to Q49), kept with the answer each got (John, 30 October). Live:
the disposable Neo4j only."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from app import graph_questions

pytestmark = pytest.mark.live
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
FIRST = {"paragraphs": [{"text": "Two writers oppose the veto.", "refs": [1]}],
         "sources": [{"id": "P1", "kind": "post", "name": "Anonymous", "date": "2026-10-29", "text": "It blocks.",
                      "href": "/issues/veto", "issue": "Security Council veto", "post_id": "post-1"}],
         "partial": None}
NEWER = {**FIRST, "paragraphs": [{"text": "Three writers oppose the veto now.", "refs": [1]}]}


@pytest.fixture
def questions(live_graph):
    live_graph.ensure_constraints(asking=True)
    return live_graph


def test_an_answered_question_is_kept_with_its_answer_and_opened_by_its_id(questions):
    first = graph_questions.keep("Why the veto?", "veto", NOW, FIRST)
    assert re.fullmatch(r"[0-9a-f]{32}", first)
    kept = graph_questions.one(first)
    assert (kept["text"], kept["issue_key"], kept["issue_name"], kept["answer"], kept["asked_at"]) == \
        ("Why the veto?", "veto", None, FIRST, NOW)
    assert graph_questions.one("0" * 32) is None


def test_asked_again_the_question_keeps_its_id_and_shows_the_newest_answer(questions):
    questions.driver().execute_query("CREATE (:Issue {key: 'veto', name: 'Security Council veto', seed: false})",
                                     database_=questions.database())
    first = graph_questions.keep("Why the veto?", "veto", NOW, FIRST)
    again = graph_questions.keep("why the  veto", "veto", NOW + timedelta(hours=1), NEWER)
    assert again == first
    kept = graph_questions.one(first)
    assert kept["answer"] == NEWER and kept["asked_at"] == NOW + timedelta(hours=1)
    assert kept["issue_name"] == "Security Council veto"
    assert graph_questions.recent("veto") == [{"text": "why the veto", "issue_key": "veto",
                                               "issue_name": "Security Council veto", "id": first, "answered": True}]


def test_a_question_kept_before_answers_were_gets_an_id_when_asked_again(questions):
    questions.driver().execute_query(
        "CREATE (:Question {key: '|who pays', text: 'Who pays?', issue_key: null, created_at: datetime($now), "
        "asked_at: datetime($now), asked: 1})", now=NOW.isoformat(), database_=questions.database())
    assert graph_questions.recent() == [{"text": "Who pays?", "issue_key": None, "issue_name": None, "id": None,
                                         "answered": False}]
    qid = graph_questions.keep("Who pays?", None, NOW + timedelta(hours=1), FIRST)
    assert graph_questions.recent()[0] == {"text": "Who pays?", "issue_key": None, "issue_name": None, "id": qid,
                                           "answered": True}


def test_question_ids_are_unique(questions):
    names = {record["name"] for record in
             questions.driver().execute_query("SHOW CONSTRAINTS", database_=questions.database()).records}
    assert {"question_key", "question_id"} <= names
