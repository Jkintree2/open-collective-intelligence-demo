"""Phase 3, ask the database: the questions people asked (03_schema.md, Phase 3, Q47 to Q49), for the list
under the Ask box (John, 28 October), each kept with the answer it got so the list can open it (John, 30
October). A question is kept only once it was answered, and never with who asked: no Person, no key, no edge.
The same question on the same issue is one Question, moved to the top, with the newest answer. Since GitHub
issue 55 a question asked on a solution's or a piece of evidence's page keeps that key instead of an issue's."""

import json
import uuid
from datetime import datetime
from typing import Any

from app.graph_runtime import _read, _write

QUESTION_MAX = 500
RECENT = 10          # on Ask the database
RECENT_ON_ISSUE = 5  # under an issue's Ask box

# Q47. One per question and issue (or the whole database); asking it again moves it up, counts it and keeps
# its newest answer. A question kept before answers were gets its id the next time it is answered.
KEEP = """
MERGE (q:Question {key: $key})
ON CREATE SET q.created_at = datetime($now), q.asked = 0
SET q.id = coalesce(q.id, $id), q.text = $text, q.issue_key = $issue_key, q.asked_at = datetime($now),
    q.asked = q.asked + 1, q.answer = $answer, q.solution_key = $solution_key, q.evidence_key = $evidence_key
RETURN q.id AS id
"""

# Q48. The latest questions, everywhere or on one issue, solution or piece of evidence, with the name of what
# each was asked on while it still exists.
RECENT_QUESTIONS = """
MATCH (q:Question)
WHERE ($issue_key IS NULL OR q.issue_key = $issue_key)
  AND ($solution_key IS NULL OR q.solution_key = $solution_key)
  AND ($evidence_key IS NULL OR q.evidence_key = $evidence_key)
WITH q ORDER BY q.asked_at DESC LIMIT $limit
OPTIONAL MATCH (i:Issue {key: q.issue_key})
OPTIONAL MATCH (s:Solution {key: q.solution_key})
OPTIONAL MATCH (e:Evidence {key: q.evidence_key})
RETURN q.text AS text, q.issue_key AS issue_key, i.name AS issue_name, q.id AS id, q.answer IS NOT NULL AS answered,
       q.solution_key AS solution_key, s.name AS solution_name, q.evidence_key AS evidence_key, e.name AS evidence_name
ORDER BY q.asked_at DESC
"""

# Q49. One question and the answer it last got, by its id.
ONE_QUESTION = """
MATCH (q:Question {id: $id})
OPTIONAL MATCH (i:Issue {key: q.issue_key})
OPTIONAL MATCH (s:Solution {key: q.solution_key})
OPTIONAL MATCH (e:Evidence {key: q.evidence_key})
RETURN q.text AS text, q.issue_key AS issue_key, i.name AS issue_name, q.answer AS answer, q.asked_at AS asked_at,
       q.solution_key AS solution_key, s.name AS solution_name, q.evidence_key AS evidence_key, e.name AS evidence_name
"""


def question_key(text: str, issue_key: str | None, *, solution_key: str | None = None,
                 evidence_key: str | None = None) -> str:
    """Spacing, case and a closing question mark do not make a question new. A key never holds a colon
    (text.make_key), so a solution's or a piece of evidence's never reads as an issue's."""
    words = " ".join(text.split()).lower().rstrip("?.! ")
    where = f"solution:{solution_key}" if solution_key else f"evidence:{evidence_key}" if evidence_key else issue_key
    return f"{where or ''}|{words}"


def keep(text: str, issue_key: str | None, now: datetime, answer: dict[str, Any], *,
         solution_key: str | None = None, evidence_key: str | None = None) -> str | None:
    """The question's id, for the link to its answer."""
    text = " ".join(text.split())[:QUESTION_MAX]
    if not text:
        return None
    rows = _write(KEEP, key=question_key(text, issue_key, solution_key=solution_key, evidence_key=evidence_key),
                  id=uuid.uuid4().hex, text=text, issue_key=issue_key, solution_key=solution_key,
                  evidence_key=evidence_key, now=now.isoformat(),
                  answer=json.dumps(answer, ensure_ascii=False, separators=(",", ":")))
    return rows[0]["id"] if rows else None


def recent(issue_key: str | None = None, limit: int = RECENT, *, solution_key: str | None = None,
           evidence_key: str | None = None) -> list[dict[str, Any]]:
    return _read(RECENT_QUESTIONS, issue_key=issue_key, solution_key=solution_key, evidence_key=evidence_key,
                 limit=limit)


def one(question_id: str) -> dict[str, Any] | None:
    rows = _read(ONE_QUESTION, id=question_id)
    if not rows:
        return None
    row = rows[0]
    row["answer"] = json.loads(row["answer"]) if row["answer"] else None
    return row
