"""Phase 3: ask the record (04_interface.md and 05_extraction.md, "Ask the record"), behind ASK_ENABLED.

GET /ask is the page for the whole record; the box on each issue page is the same form with the issue's
key. ask.js posts to /api/ask and shows the answer in place; without JavaScript the form posts to /ask
and the answer comes back on the Ask page. A question that was answered is kept, without who asked, for
the list under the box (John, 28 October); answers and digests live only in the request (the browser
holds the visit's earlier questions)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, replace
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app import ask, config, graph, graph_questions
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


def run(request: Request, question: str, earlier: list[str], issue: str | None) -> tuple[int, dict]:
    """The answer as the page shows it, with its status code. Checks run in the order the page lists its
    lines; the reading service is counted only when it is called."""
    question = " ".join(question.split())
    if not question:
        return 400, {"message": NO_QUESTION}
    if len(question) > ask.QUESTION_MAX:
        return 400, {"message": TOO_LONG}
    issue_name = None
    if issue:
        header = graph.issue_header(issue)
        if header is None:
            raise HTTPException(404)
        issue_name = header["name"]
    settings = config.get_settings()
    if not settings.llm_api_key:
        return 200, {"message": NO_SERVICE}
    digest = ask.issue_digest(issue) if issue else ask.record_digest(question)
    if digest is None:
        raise HTTPException(404)
    # Nothing to answer from: the empty line, with no call and no count. A question about a guiding
    # document can still be answered from the document (John, 28 October).
    if digest.empty and not ask.names_document(question):
        return 200, {"status": "empty", "message": ask.EMPTY, "paragraphs": [], "sources": [], "partial": None,
                     "issue": issue_name}
    if (refused := _take(reader_key(request))) is not None:
        return 429, {"message": refused}
    result = ask.answer(question, earlier, digest, settings, scope="issue" if issue else "record",
                        request_id=getattr(request.state, "request_id", None))
    if result.status == "answered":
        _keep(request, question, issue)
    return 200, {"status": result.status, "message": result.message, "paragraphs": result.paragraphs,
                 "sources": [{**asdict(_linked(source, settings)), "when": source.when} for source in result.sources],
                 "partial": ask.PARTIAL if result.partial else None, "issue": issue_name}


def _keep(request: Request, question: str, issue: str | None) -> None:
    """The answer is shown whatever happens here: a question that cannot be kept is only logged."""
    try:
        graph_questions.keep(question, issue, datetime.now(timezone.utc))
    except Exception as exc:  # noqa: BLE001
        log.warning(json.dumps({"event": "question_not_kept", "request_id": getattr(request.state, "request_id", None),
                                "error": type(exc).__name__}))


def recent_questions(issue: str | None) -> list[dict]:
    """The list under the box; a page without it is still the Ask page."""
    try:
        return graph_questions.recent(issue, graph_questions.RECENT_ON_ISSUE if issue else graph_questions.RECENT)
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
             earlier: list[str] = Form(default_factory=list, max_length=20)) -> Response:
    """Without JavaScript: the answer on the Ask page, with a way back to the issue it was asked on. The
    page carries the last three questions (never the answers) in hidden fields, as the box does with it."""
    earlier = [text[:ask.QUESTION_MAX] for text in earlier if text.strip()][-ask.EARLIER_MAX:]
    status, body = run(request, question, earlier, issue or None)
    asked = " ".join(question.split())
    carried = (earlier + [asked])[-ask.EARLIER_MAX:] if body.get("status") else earlier
    return page(request, "ask.html", {"result": body, "question": asked, "earlier": carried,
                                      "issue": {"key": issue, "name": body.get("issue")} if issue else None,
                                      "recent_questions": recent_questions(issue or None)},
                status_code=status)


@router.post("/api/ask", dependencies=[Depends(ask_on), Depends(require_access), Depends(require_same_origin)])
def ask_api(request: Request, data: AskRequest) -> Response:
    status, body = run(request, data.question, data.earlier, data.issue)
    return JSONResponse(body, status_code=status)
