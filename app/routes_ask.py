"""Phase 3: ask the record (04_interface.md and 05_extraction.md, "Ask the record"), behind ASK_ENABLED.

GET /ask is the page for the whole record; the box on each issue page is the same form with the issue's
key. ask.js posts to /api/ask and shows the answer in place; without JavaScript the form posts to /ask
and the answer comes back on the Ask page. A question that was answered is kept, without who asked, for
the list under the box (John, 28 October), with the answer it got, which GET /ask/answers/<id> shows while
the posts it cites are as they were (John, 30 October). Digests live only in the request (the browser holds
the visit's earlier questions)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app import ask, config, graph, graph_ask, graph_item_pages, graph_questions
from app.auth import DailyLimit, KeyedLimit, MinuteBucket
from app.members import require_access, require_same_origin
from app.pages import page
from app.routes_evidence import reader_key

router = APIRouter()
log = logging.getLogger("oci")
# Client facing copy, word for word from docs/planning/04_interface.md.
NO_QUESTION = "Please write a question."
TOO_LONG = "Please keep the question under 500 characters."
PERSON_LIMIT = "You have asked 30 questions today. Please ask again tomorrow."
SITE_LIMIT = "The site has answered as many questions as it can today. Please ask again tomorrow."
NO_SERVICE = "Asking needs the language model, which is not set up."
ANSWERED_ON = "Answered on {day}. The database may have changed since, so ask again for an answer from what it holds now."
ANSWER_CHANGED = ("A post this answer rested on has been edited or removed since, so the answer is no longer shown. "
                  "Ask again for an answer from what the database holds now.")
_QUESTION_ID = re.compile(r"[0-9a-f]{32}")

# 30 questions a person a day and 300 for the site, held in this process: a restart or a wake from
# Render's sleep starts both counts again, so they are a ceiling per waking (the logs hold the real count).
person_limit = KeyedLimit(30, 86400)
# Five a minute: each call can hold a worker for 40 seconds, and Render's free plan has a tenth of a CPU.
site_minute = MinuteBucket(capacity=5, period=60.0)
site_daily = DailyLimit(capacity=300)


def ask_on() -> None:
    if not config.get_settings().ask_enabled:
        raise HTTPException(404)


class AskRequest(BaseModel):
    question: str = Field(default="", max_length=5000)
    earlier: list[str] = Field(default_factory=list, max_length=20)
    issue: str | None = Field(default=None, max_length=200)
    # GitHub issue 55: the box on a solution's or a piece of evidence's page.
    solution: str | None = Field(default=None, max_length=400)
    evidence: str | None = Field(default=None, max_length=400)


def _take(key: str) -> str | None:
    """The person's count, then the site's; a question the site refuses is not counted for the person.
    The site's day full says so; its minute full (five a minute) is "try again in a minute"."""
    if not person_limit.take(key):
        return PERSON_LIMIT
    if not site_daily.take(site_minute):
        person_limit.give_back(key)
        return SITE_LIMIT if site_daily.used >= site_daily.capacity else ask.FAILED
    return None


def _linked(source: ask.Source, settings: config.Settings) -> ask.Source:
    """A guiding document links to its place on the About page only while that page is switched on."""
    if source.kind == "document" and not settings.about_enabled:
        return replace(source, href=None)
    return source


def _kept(source: ask.Source) -> dict[str, Any]:
    """A source as an answer keeps it. Only a solution or a piece of evidence has a page of its own (GitHub issue
    55), so a post or a document is kept as it was before."""
    kept = asdict(source)
    if kept["page"] is None:
        del kept["page"]
    return kept


def _shown(source: ask.Source, settings: config.Settings) -> dict[str, Any]:
    """A source as the page shows it; a post's id stays on the server."""
    shown = {**_kept(_linked(source, settings)), "when": source.when}
    del shown["post_id"]
    return shown


def _about(issue: str | None, solution: str | None, evidence: str | None) -> dict[str, str] | None:
    """What the question was asked on, {kind, key, name}, or None for the whole record; not found when it is
    not in the record."""
    if issue:
        header = graph.issue_header(issue)
        kind, key, name = "issue", issue, header and header["name"]
    elif solution:
        row = graph_item_pages.solution(solution)
        kind, key, name = "solution", solution, row and row["name"]
    elif evidence:
        row = graph_item_pages.evidence(evidence)
        kind, key, name = "evidence", evidence, row and row["name"]
    else:
        return None
    if not name:
        raise HTTPException(404)
    return {"kind": kind, "key": key, "name": name}


DIGESTS = {"issue": "issue_digest", "solution": "solution_digest", "evidence": "evidence_digest"}


def _on(issue: str | None, solution: str | None, evidence: str | None) -> dict[str, str]:
    """A box on a solution's or a piece of evidence's page: {"solution": key} or {"evidence": key}. An issue's box
    sends neither, so an issue wins."""
    if issue:
        return {}
    return {"solution": solution} if solution else {"evidence": evidence} if evidence else {}


def run(request: Request, question: str, earlier: list[str], issue: str | None,
        solution: str | None = None, evidence: str | None = None) -> tuple[int, dict]:
    """The answer as the page shows it, with its status code. Checks run in the order the page lists its
    lines; the reading service is counted only when it is called. A question asked on a solution's or a
    piece of evidence's page (GitHub issue 55) is answered from what it holds, and its body names it."""
    question = " ".join(question.split())
    if not question:
        return 400, {"message": NO_QUESTION}
    if len(question) > ask.QUESTION_MAX:
        return 400, {"message": TOO_LONG}
    about = _about(issue, solution, evidence)
    named = {"issue": about["name"] if about and about["kind"] == "issue" else None}
    if about and about["kind"] != "issue":
        named[about["kind"]] = about["name"]
    settings = config.get_settings()
    if not settings.llm_api_key:
        return 200, {"message": NO_SERVICE}
    digest = getattr(ask, DIGESTS[about["kind"]])(about["key"]) if about else ask.record_digest(question)
    if digest is None:
        raise HTTPException(404)
    # Nothing to answer from: the empty line, with no call and no count. A question about a guiding
    # document can still be answered from the document (John, 28 October).
    if digest.empty and not ask.names_document(question):
        return 200, {"status": "empty", "message": ask.EMPTY, "paragraphs": [], "sources": [], "partial": None,
                     **named}
    if (refused := _take(reader_key(request))) is not None:
        return 429, {"message": refused}
    result = ask.answer(question, earlier, digest, settings, scope=about["kind"] if about else "record",
                        request_id=getattr(request.state, "request_id", None))
    partial = ask.PARTIAL if result.partial else None
    question_id = None
    if result.status == "answered":
        on = {f"{about['kind']}_key": about["key"]} if about and about["kind"] != "issue" else {}
        question_id = _keep(request, question, issue, {"paragraphs": result.paragraphs, "partial": partial,
                                                       "sources": [_kept(source) for source in result.sources]}, **on)
    return 200, {"status": result.status, "message": result.message, "paragraphs": result.paragraphs,
                 "sources": [_shown(source, settings) for source in result.sources],
                 "partial": partial, **named, "question_id": question_id}


def _keep(request: Request, question: str, issue: str | None, answer: dict[str, Any], **on: str) -> str | None:
    """The question's id. The answer is shown whatever happens here: a question that cannot be kept is only
    logged, and listed without a link. `on` is a solution's or a piece of evidence's key (GitHub issue 55)."""
    try:
        return graph_questions.keep(question, issue, datetime.now(timezone.utc), answer, **on)
    except Exception as exc:  # noqa: BLE001
        log.warning(json.dumps({"event": "question_not_kept", "request_id": getattr(request.state, "request_id", None),
                                "error": type(exc).__name__}))
        return None


def _still_holds(answer: dict[str, Any], asked_at: datetime) -> bool:
    """A kept answer may quote or name the posts it cites, so it is shown only while each is there, unedited
    since and under the same name: an answer must not keep what a writer has since taken back."""
    cited = {source["post_id"]: source["name"] for source in answer["sources"] if source["kind"] == "post"}
    if not cited:
        return True
    posts = {post["id"]: post for post in graph_ask.posts_by_ids(list(cited))}
    return all(pid in posts and ask._who(posts[pid]) == name
               and (posts[pid].get("edited_at") is None or posts[pid]["edited_at"] <= asked_at)
               for pid, name in cited.items())


def recent_questions(issue: str | None, **on: str) -> list[dict]:
    """The list under the box; a page without it is still the Ask page. `on` is solution_key or evidence_key for
    the box on that page (GitHub issue 55)."""
    try:
        return graph_questions.recent(issue, graph_questions.RECENT_ON_ISSUE if issue or on else graph_questions.RECENT,
                                      **on)
    except Exception as exc:  # noqa: BLE001
        log.warning(json.dumps({"event": "questions_not_read", "error": type(exc).__name__}))
        return []


@router.get("/ask", dependencies=[Depends(ask_on), Depends(require_access)])
def ask_page(request: Request) -> Response:
    return page(request, "ask.html", {"result": None, "question": "", "issue": None, "earlier": [],
                                      "recent_questions": recent_questions(None)})


@router.post("/ask", dependencies=[Depends(ask_on), Depends(require_access), Depends(require_same_origin)])
def ask_form(request: Request, question: str = Form("", max_length=5000),
             issue: str = Form("", max_length=200),
             solution: str = Form("", max_length=400), evidence: str = Form("", max_length=400),
             earlier: list[str] = Form(default_factory=list, max_length=20)) -> Response:
    """Without JavaScript: the answer on the Ask page, with a way back to the issue, solution or piece of
    evidence it was asked on. The page carries the last three questions (never the answers) in hidden fields,
    as the box does with it."""
    earlier = [text[:ask.QUESTION_MAX] for text in earlier if text.strip()][-ask.EARLIER_MAX:]
    issue = issue or None
    on = _on(issue, solution, evidence)
    status, body = run(request, question, earlier, issue, **on)
    asked = " ".join(question.split())
    carried = (earlier + [asked])[-ask.EARLIER_MAX:] if body.get("status") else earlier
    about = {kind: {"key": key, "name": body.get(kind)} for kind, key in on.items()}
    return page(request, "ask.html", {"result": body, "question": asked, "earlier": carried,
                                      "issue": {"key": issue, "name": body.get("issue")} if issue else None,
                                      "solution": about.get("solution"), "evidence": about.get("evidence"),
                                      "recent_questions": recent_questions(
                                          issue, **{f"{kind}_key": key for kind, key in on.items()})},
                status_code=status)


@router.get("/ask/answers/{question_id}", dependencies=[Depends(ask_on), Depends(require_access)])
def answer_page(request: Request, question_id: str) -> Response:
    """John, 30 October: a listed question opens the answer it got, with Ask again for a fresh one. Its issue
    shows while it still exists; a question kept before answers were has no page."""
    kept = graph_questions.one(question_id) if _QUESTION_ID.fullmatch(question_id) else None
    if kept is None or not kept["answer"]:
        raise HTTPException(404)
    answer, settings = kept["answer"], config.get_settings()
    result = {"status": "answered", "message": None, "paragraphs": answer["paragraphs"], "partial": answer["partial"],
              "sources": [_shown(ask.Source(**source), settings) for source in answer["sources"]]} \
        if _still_holds(answer, kept["asked_at"]) else None
    return page(request, "ask_answer.html", {
        "question": kept["text"], "result": result, "changed": ANSWER_CHANGED,
        "answered_on": ANSWERED_ON.format(day=ask.day_words(kept["asked_at"].date())),
        "issue": {"key": kept["issue_key"], "name": kept["issue_name"]} if kept["issue_name"] else None,
        # GitHub issue 55: asked on a solution's or a piece of evidence's page, while it still exists.
        "solution": {"key": kept["solution_key"], "name": kept["solution_name"]} if kept.get("solution_name") else None,
        "evidence": {"key": kept["evidence_key"], "name": kept["evidence_name"]} if kept.get("evidence_name") else None})


@router.post("/api/ask", dependencies=[Depends(ask_on), Depends(require_access), Depends(require_same_origin)])
def ask_api(request: Request, data: AskRequest) -> Response:
    status, body = run(request, data.question, data.earlier, data.issue,
                       **_on(data.issue, data.solution, data.evidence))
    return JSONResponse(body, status_code=status)
