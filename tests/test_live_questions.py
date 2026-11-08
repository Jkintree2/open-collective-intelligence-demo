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
# GitHub issue 55: a question asked on a solution's or a piece of evidence's page names it instead.
NOT_ON_A_SOLUTION = {"solution_key": None, "solution_name": None, "evidence_key": None, "evidence_name": None}


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
                                               "issue_name": "Security Council veto", "id": first, "answered": True,
                                               **NOT_ON_A_SOLUTION, "asked_at": NOW + timedelta(hours=1)}]


def test_a_question_kept_before_answers_were_gets_an_id_when_asked_again(questions):
    questions.driver().execute_query(
        "CREATE (:Question {key: '|who pays', text: 'Who pays?', issue_key: null, created_at: datetime($now), "
        "asked_at: datetime($now), asked: 1})", now=NOW.isoformat(), database_=questions.database())
    assert graph_questions.recent() == [{"text": "Who pays?", "issue_key": None, "issue_name": None, "id": None,
                                         "answered": False, **NOT_ON_A_SOLUTION, "asked_at": NOW}]
    qid = graph_questions.keep("Who pays?", None, NOW + timedelta(hours=1), FIRST)
    assert graph_questions.recent()[0] == {"text": "Who pays?", "issue_key": None, "issue_name": None, "id": qid,
                                           "answered": True, **NOT_ON_A_SOLUTION, "asked_at": NOW + timedelta(hours=1)}


def test_question_ids_are_unique(questions):
    names = {record["name"] for record in
             questions.driver().execute_query("SHOW CONSTRAINTS", database_=questions.database()).records}
    assert {"question_key", "question_id"} <= names


# v0.3 (John, 7 November: "My posts" lists his questions too). A member for whom Home is on is linked to each question
# they ask (Q56), once, with when they last asked it, and reads them back newest first on any device (Q57).
def member(questions, key):
    questions.driver().execute_query("CREATE (:Person {key: $key, name: $key, email: $email})", key=key,
                                     email=f"{key[5:]}@example.org", database_=questions.database())


def asked_links(questions, key):
    return questions.driver().execute_query("MATCH (:Person {key: $key})-[a:ASKED]->(:Question) RETURN count(a) AS n",
                                            key=key, database_=questions.database()).records[0]["n"]


def test_a_member_is_linked_once_to_each_question_and_reads_them_newest_first(questions):
    member(questions, "acct:ada")
    member(questions, "acct:bob")
    veto = graph_questions.keep("Why the veto?", "veto", NOW, FIRST, person_key="acct:ada")
    pays = graph_questions.keep("Who pays?", None, NOW + timedelta(hours=1), FIRST, person_key="acct:ada")
    graph_questions.keep("Is it fair?", None, NOW + timedelta(hours=2), FIRST, person_key="acct:bob")
    mine = graph_questions.mine("acct:ada", 10)
    assert [(row["text"], row["id"], row["answered"], row["asked_at"]) for row in mine] == \
        [("Who pays?", pays, True, NOW + timedelta(hours=1)), ("Why the veto?", veto, True, NOW)]
    assert mine[1]["issue_key"] == "veto" and mine[0]["issue_key"] is None
    # Asked again later: still one link, moved to the top with the new time and the newest wording.
    graph_questions.keep("why the  veto", "veto", NOW + timedelta(hours=3), NEWER, person_key="acct:ada")
    assert [(row["text"], row["asked_at"]) for row in graph_questions.mine("acct:ada", 10)] == \
        [("why the veto", NOW + timedelta(hours=3)), ("Who pays?", NOW + timedelta(hours=1))]
    assert asked_links(questions, "acct:ada") == 2
    # Bob asking Ada's question links Bob too; Ada's own time for it does not move.
    graph_questions.keep("Who pays?", None, NOW + timedelta(hours=4), FIRST, person_key="acct:bob")
    assert graph_questions.mine("acct:ada", 10)[1]["asked_at"] == NOW + timedelta(hours=1)
    assert [row["text"] for row in graph_questions.mine("acct:bob", 10)] == ["Who pays?", "Is it fair?"]
    assert len(graph_questions.mine("acct:ada", 1)) == 1


def test_without_a_member_nobody_is_linked(questions):
    member(questions, "acct:ada")
    graph_questions.keep("Why the veto?", "veto", NOW, FIRST)
    graph_questions.keep("Who pays?", None, NOW, FIRST, person_key="acct:nobody")
    total = questions.driver().execute_query("MATCH ()-[a:ASKED]->() RETURN count(a) AS n",
                                             database_=questions.database()).records[0]["n"]
    assert total == 0 and graph_questions.mine("acct:ada", 10) == []
    assert len(graph_questions.recent()) == 2
