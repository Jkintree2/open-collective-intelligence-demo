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
from typing import AsyncIterator
from urllib.parse import quote, unquote

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import graph
from app.auth import (
    GATE_COOKIE,
    GATE_SECONDS,
    WRONG_PASSPHRASE_DELAY,
    GateRequired,
    attempt_bucket,
    make_gate_token,
    passphrase_matches,
    require_gate,
)
from app.config import get_settings
from app.graph import RecordAsleep
from app.text import clean_name, make_key, relative_time

settings = get_settings()

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.globals["site_name"] = settings.site_name

TEXT_MAX = 4000
FEED_LIMIT = 60
NAME_COOKIE = "oci_name"
ANON_COOKIE = "oci_anon"
YEAR_SECONDS = 365 * 86400

# Client facing copy, word for word from docs/planning/04_interface.md.
WRONG_PASSPHRASE = "That passphrase did not match. Check the message from John and try again."
TOO_LONG = "That is longer than this demo can read at once. Please shorten it to a few paragraphs."
# Not in the interface doc: shown when the passphrase bucket is empty.
TOO_MANY_TRIES = "Too many tries. Please wait a minute and try again."

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


def _render_index(
    request: Request, *, message: str | None = None, text: str = "", status_code: int = 200
) -> Response:
    posts = graph.list_posts(FEED_LIMIT)
    now = datetime.now(timezone.utc)
    for post in posts:
        created = post.get("created_at")
        post["when"] = relative_time(created, now) if created else ""
        post["absolute"] = created.strftime("%Y-%m-%d %H:%M UTC") if created else ""
        post["iso"] = created.isoformat() if created else ""
    name = unquote(request.cookies.get(NAME_COOKIE, ""))
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "site_sentence": settings.site_sentence,
            "posts": posts,
            "name": name,
            "message": message,
            "text": text,
        },
        status_code=status_code,
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
    text = text.strip()
    if len(text) > TEXT_MAX:
        return _render_index(request, message=TOO_LONG, text=text, status_code=413)
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


@app.exception_handler(GateRequired)
async def gate_redirect(_: Request, exc: GateRequired) -> Response:
    return RedirectResponse(f"/enter?next={quote(exc.next_path, safe='/')}", status_code=303)


@app.exception_handler(RecordAsleep)
async def record_asleep(request: Request, exc: RecordAsleep) -> Response:
    log.warning(
        json.dumps({"event": "record_asleep", "request_id": _request_id(request), "error": str(exc)})
    )
    if request.url.path == "/health":
        return JSONResponse({"ok": False}, status_code=503)
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
    return templates.TemplateResponse(request, "error.html", {}, status_code=500)
