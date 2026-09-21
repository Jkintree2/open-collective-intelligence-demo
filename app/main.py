"""FastAPI app: lifespan, one JSON log line per request, routes, error and asleep pages."""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Literal
from dataclasses import asdict
from urllib.parse import quote, unquote

from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app import graph, extract as reading
from app.extract import CardPayload, resolve_payload
from app.auth import (
    GATE_COOKIE,
    GATE_SECONDS,
    WRONG_PASSPHRASE_DELAY,
    GateRequired,
    attempt_bucket,
    make_gate_token,
    passphrase_matches,
    require_gate,
    reading_limit,
)
from app.config import get_settings
from app.graph import RecordAsleep
from app.text import clean_name, count_line, make_key, relative_time, sentences

settings = get_settings()

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.globals["site_name"] = settings.site_name

TEXT_MAX = 4000
FEED_LIMIT = 60
CHIP_LIMIT = 5
SORTS = (("people", "Most people"), ("recent", "Most recent"), ("evidence", "Most evidence"))
# Display verbs from docs/planning/03_schema.md; PART_OF has no sentence.
VERBS = {
    "CLAIM": "claims",
    "SUBMIT": "submits",
    "PROPOSE": "proposes",
    "HAVE_PROPOSED": "has proposed",
    "SUPPORTS": "supports",
    "REFUTES": "refutes",
    "APPROVE": "approves",
    "OPPOSE": "opposes",
}
NAME_COOKIE = "oci_name"
ANON_COOKIE = "oci_anon"
YEAR_SECONDS = 365 * 86400

# Client facing copy, word for word from docs/planning/04_interface.md.
WRONG_PASSPHRASE = "That passphrase did not match. Check the message from John and try again."
TOO_LONG = "That is longer than this demo can read at once. Please shorten it to a few paragraphs."
# Not in the interface doc: shown when the passphrase bucket is empty.
TOO_MANY_TRIES = "Too many tries. Please wait a minute and try again."
NOT_ANSWERING = "The reading service is not answering right now. You can fill in the form by hand, or try again in a minute."
NOT_FOUND = "We could not find an issue, a claim, evidence or a solution in that. If you meant to make one, fill in the form below, or change the text and read it again."
ENGLISH_ONLY = "This demo reads English only for now."
READING_LIMIT = "Too many requests. Please wait a minute or fill in the form by hand."

log = logging.getLogger("oci")


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.handlers[:] = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
    # One line per request comes from the middleware below.
    logging.getLogger("uvicorn.access").disabled = True


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    graph.open_driver(settings)
    try:
        graph.ensure_constraints()
    except RecordAsleep as exc:
        log.warning(json.dumps({"event": "constraints_skipped", "error": str(exc)}))
    yield
    graph.close_driver()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.middleware("http")
async def log_request(request: Request, call_next):  # type: ignore[no-untyped-def]
    request.state.request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        log.info(
            json.dumps(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "ms": round((time.perf_counter() - started) * 1000),
                    "request_id": request.state.request_id,
                }
            )
        )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _set_cookie(response: Response, key: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key,
        value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=not settings.is_local,
    )


def _safe_next(next_path: str | None) -> str:
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/"


def _issue_href(key: str | None) -> str:
    return f"/issues/{quote(key, safe='')}" if key else "/issues"


def _decorate_posts(posts: list[dict]) -> list[dict]:
    """Relative times, chips and the sentence list for a page of posts."""
    now = datetime.now(timezone.utc)
    structure = graph.post_structure([post["id"] for post in posts])
    for post in posts:
        created = post.get("created_at")
        post["when"] = relative_time(created, now) if created else ""
        post["absolute"] = created.strftime("%Y-%m-%d %H:%M UTC") if created else ""
        post["iso"] = created.isoformat() if created else ""
        rows = structure.get(post["id"], [])
        issue_keys = [r["to_key"] for r in rows if r["rel"] == "CLAIM"]
        first_issue = issue_keys[0] if issue_keys else None
        chips: dict[tuple[str, str], dict] = {}
        sentences: list[str] = []
        for row in rows:
            for label, key, name, home in (
                (row["from_label"], row["from_key"], row["from_name"], None),
                (row["to_label"], row["to_key"], row["to_name"], row.get("home_key")),
            ):
                if label not in ("Issue", "Solution", "Evidence") or not key or (label, key) in chips:
                    continue
                if label == "Issue":
                    href = _issue_href(key)
                elif label == "Solution":
                    href = _issue_href(home or first_issue)
                else:
                    target = row["to_key"] if row["to_label"] == "Issue" else row.get("home_key")
                    href = _issue_href(target or first_issue)
                chips[(label, key)] = {"label": label, "key": key, "name": name, "href": href}
            verb = VERBS.get(row["rel"])
            if verb:
                subject = "Anonymous" if row["from_label"] == "Person" and row.get("anonymous") else row["from_name"]
                sentences.append(f"{subject or 'Anonymous'} {verb} {row['to_name']}")
        post["chips"] = list(chips.values())
        post["sentences"] = sentences
    return posts


def _render_index(
    request: Request, *, message: str | None = None, text: str = "", status_code: int = 200
) -> Response:
    posts = _decorate_posts(graph.list_posts(FEED_LIMIT))
    chips = graph.top_issues(CHIP_LIMIT)
    name = unquote(request.cookies.get(NAME_COOKIE, ""))
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "site_sentence": settings.site_sentence,
            "posts": posts,
            "chips": chips,
            "name": name,
            "message": message,
            "text": text,
        },
        status_code=status_code,
    )


@app.get("/issues", response_class=HTMLResponse, dependencies=[Depends(require_gate)])
def issues_page(request: Request, sort: str = Query("people")) -> Response:
    sort = sort if sort in graph.SORTS else "people"
    grouped = graph.group_issues(graph.list_issues(), sort)
    for issue in grouped:
        issue["line"] = count_line(issue)
        for child in issue["children"]:
            child["line"] = count_line(child)
    return templates.TemplateResponse(
        request, "issues.html", {"issues": grouped, "sort": sort, "sorts": SORTS}
    )


@app.get("/issues/{key}", response_class=HTMLResponse, dependencies=[Depends(require_gate)])
def issue_page(request: Request, key: str) -> Response:
    header = graph.issue_header(key)
    if header is None:
        return RedirectResponse("/issues", status_code=303)
    return templates.TemplateResponse(
        request,
        "issue.html",
        {
            "issue": header,
            "claimants": graph.issue_claimants(key),
            "solutions": graph.issue_solutions(key),
            "evidence": graph.issue_evidence(key),
            "posts": _decorate_posts(graph.issue_posts(key, FEED_LIMIT)),
        },
    )


@app.get("/enter", response_class=HTMLResponse)
def enter_form(request: Request, next: str = "/") -> Response:
    return templates.TemplateResponse(
        request, "enter.html", {"next": _safe_next(next), "message": None}
    )


@app.post("/enter")
def enter_submit(
    request: Request, passphrase: str = Form(""), next: str = Form("/")
) -> Response:
    target = _safe_next(next)
    if passphrase_matches(passphrase):
        response = RedirectResponse(target, status_code=303)
        _set_cookie(response, GATE_COOKIE, make_gate_token(), GATE_SECONDS)
        return response
    if not attempt_bucket.take():
        return templates.TemplateResponse(
            request, "enter.html", {"next": target, "message": TOO_MANY_TRIES}, status_code=429
        )
    time.sleep(WRONG_PASSPHRASE_DELAY)
    return templates.TemplateResponse(
        request, "enter.html", {"next": target, "message": WRONG_PASSPHRASE}
    )


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_gate)])
def write_page(request: Request) -> Response:
    return _render_index(request)


def _valid_anon_id(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


@app.post("/posts", dependencies=[Depends(require_gate)])
def create_post(
    request: Request,
    display_name: str = Form(""),
    anonymous: str | None = Form(None),
    text: str = Form(""),
) -> Response:
    if len(text) > TEXT_MAX:
        return _render_index(request, message=TOO_LONG, text=text, status_code=413)
    text = text.strip()
    if not text:
        return RedirectResponse("/", status_code=303)
    name = clean_name(display_name)
    # A ticked box, an empty name or a name with no usable key all post anonymously.
    post_anonymously = bool(anonymous) or make_key(name) is None
    response = RedirectResponse("/", status_code=303)
    if post_anonymously:
        anon_id = _valid_anon_id(request.cookies.get(ANON_COOKIE)) or str(uuid.uuid4())
        key = graph.person_key(None, True, anon_id)
        graph.create_raw_post(key, None, True, None, text)
        _set_cookie(response, ANON_COOKIE, anon_id, YEAR_SECONDS)
    else:
        key = graph.person_key(name, False, None)
        graph.create_raw_post(key, name, False, name, text)
        _set_cookie(response, NAME_COOKIE, quote(name), YEAR_SECONDS)
    return response


@app.get("/health")
def health_check() -> dict[str, object]:
    return {"ok": True, "nodes": graph.health()}


class ReadingRequest(BaseModel):
    text: str
    display_name: str = Field(default="", max_length=120)
    anonymous: bool = False
    issue: str | None = Field(default=None, max_length=200)


class PostRequest(CardPayload):
    text: str
    display_name: str = Field(default="", max_length=120)
    anonymous: bool = False
    source: Literal["model", "manual"] = "manual"
    extraction_raw: str | None = Field(default=None, max_length=32000)
    model: str | None = Field(default=None, max_length=120)
    latency_ms: int | None = Field(default=None, ge=0, le=300000)
    plain: bool = False


def _text_error(text: str, *, allow_empty: bool = False) -> Response | None:
    if len(text) > TEXT_MAX:
        return JSONResponse({"message": TOO_LONG}, status_code=413)
    if not text.strip() and not allow_empty:
        return JSONResponse({"message": "Please write a statement first."}, status_code=422)
    return None


def _poster(data: ReadingRequest | PostRequest) -> tuple[str | None, bool]:
    name = clean_name(data.display_name)
    anonymous = data.anonymous or make_key(name) is None
    return (None if anonymous else name), anonymous


@app.get("/api/candidates", dependencies=[Depends(require_gate)])
def card_candidates() -> dict:
    return asdict(graph.candidates())


@app.post("/api/extract", dependencies=[Depends(require_gate)])
def read_statement(request: Request, data: ReadingRequest) -> Response:
    error = _text_error(data.text)
    if error is not None:
        return error
    # The budget belongs to the reading service. Without a key the card opens empty and no
    # request is made, so that path must not spend anyone's allowance.
    if settings.llm_api_key and not reading_limit.take(attempt_bucket):
        return JSONResponse({"message": READING_LIMIT}, status_code=429)
    name, _ = _poster(data)
    candidates = graph.candidates() if settings.llm_api_key else reading.Candidates.empty()
    result = reading.extract(data.text, name or "Anonymous", candidates, settings,
                             request_id=_request_id(request), writing_about=data.issue)
    if result is None:
        return JSONResponse({"payload": {"found": False}, "message": NOT_ANSWERING, "source": "manual"})
    message = ENGLISH_ONLY if not result.payload.language_ok else NOT_FOUND if not result.payload.found else ""
    return JSONResponse({"payload": result.payload.model_dump(), "message": message,
                         "source": "model" if result.payload.found else "manual", "extraction_raw": result.extraction_raw,
                         "model": result.model, "latency_ms": result.latency_ms, "shortened": result.shortened})


def _card_result(data: PostRequest):
    candidates = graph.candidates()
    incoming = data.model_copy(update={"found": True, "language_ok": True})
    resolved = resolve_payload(incoming, candidates)
    card = reading.prepared_card(incoming, candidates)
    return candidates, resolved, card


@app.post("/api/preview", dependencies=[Depends(require_gate)])
def preview_card(data: PostRequest) -> Response:
    error = _text_error(data.text, allow_empty=True)
    if error is not None:
        return error
    _, resolved, card = _card_result(data)
    name, _ = _poster(data)
    valid = not resolved.dropped and (not resolved.is_empty or bool(data.plain and data.text.strip()))
    return JSONResponse({"sentences": sentences(card, name or "Anonymous"), "valid": valid,
                         "dropped": resolved.dropped, "corrected": resolved.corrected,
                         "payload": card.model_dump()})


@app.post("/api/posts", dependencies=[Depends(require_gate)])
def post_card(request: Request, data: PostRequest) -> Response:
    error = _text_error(data.text, allow_empty=True)
    if error is not None:
        return error
    candidates, resolved, card = _card_result(data)
    if resolved.dropped or (resolved.is_empty and not (data.plain and data.text.strip())):
        return JSONResponse({"message": "Please check the form before posting.",
                             "dropped": resolved.dropped}, status_code=422)
    name, anonymous = _poster(data)
    anon_id = (_valid_anon_id(request.cookies.get(ANON_COOKIE)) or str(uuid.uuid4())) if anonymous else None
    source = data.source if not resolved.is_empty else "manual"
    extraction_raw = data.extraction_raw
    # An empty box means nothing was read: the card is the tester's own, and its sentences
    # become the statement so the post reads like every other one.
    statement = data.text.strip() or ". ".join(sentences(card, name or "Anonymous")) + "."
    if not data.text.strip():
        source, extraction_raw = "manual", None
    edited = False
    if extraction_raw:
        try:
            original = reading.prepared_card(reading.parse_payload(extraction_raw), candidates, data.text)
            edited = any(getattr(original, key) != getattr(card, key) for key in ("issues", "solutions", "evidence"))
        except ValueError:
            edited = True
    # What the reading service returned is kept whenever it returned something, even when the
    # tester emptied the card, so "it did something weird" can be answered from the one post.
    post_id = graph.merge_post(graph.person_key(name, anonymous, anon_id), name, anonymous, name,
                               statement, resolved, source=source,
                               extraction_raw=extraction_raw, model=data.model,
                               latency_ms=data.latency_ms,
                               request_id=_request_id(request), edited=edited)
    response = JSONResponse({"id": post_id, "message": "Added to the record"}, status_code=201)
    if anonymous:
        _set_cookie(response, ANON_COOKIE, anon_id, YEAR_SECONDS)
    else:
        _set_cookie(response, NAME_COOKIE, quote(name), YEAR_SECONDS)
    return response


@app.get("/feed", dependencies=[Depends(require_gate)])
def feed(request: Request) -> Response:
    return templates.TemplateResponse(request, "_feed.html", {"posts": _decorate_posts(graph.list_posts(FEED_LIMIT))})


@app.exception_handler(GateRequired)
async def gate_redirect(request: Request, exc: GateRequired) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"message": "Please enter the passphrase again.", "redirect": "/enter"}, status_code=401)
    return RedirectResponse(f"/enter?next={quote(exc.next_path, safe='/')}", status_code=303)


@app.exception_handler(RecordAsleep)
async def record_asleep(request: Request, exc: RecordAsleep) -> Response:
    log.warning(
        json.dumps({"event": "record_asleep", "request_id": _request_id(request), "error": str(exc)})
    )
    if request.url.path == "/health":
        return JSONResponse({"ok": False}, status_code=503)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"message": "The record is asleep. John needs to press Play in the Neo4j console, and it wakes up in a few minutes."}, status_code=503)
    return templates.TemplateResponse(request, "asleep.html", {}, status_code=503)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> Response:
    log.error(
        json.dumps(
            {
                "event": "error",
                "request_id": _request_id(request),
                "traceback": "".join(traceback.format_exception(exc)),
            }
        )
    )
    if request.url.path.startswith("/api/"):
        return JSONResponse({"message": "Something went wrong. Please try again in a minute."}, status_code=500)
    return templates.TemplateResponse(request, "error.html", {}, status_code=500)

# Imported after app/templates exist; admin imports templates only when rendering.
from app.admin import router as admin_router
app.include_router(admin_router)
