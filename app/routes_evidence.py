"""Phase 2: POST /api/check-evidence reads the page behind one evidence link on the card."""

from __future__ import annotations

import hashlib
from dataclasses import replace

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app import check, config, fetch_pdf, graph
from app.auth import DailyLimit, KeyedLimit, MinuteBucket
from app.fetch_page import fetch
from app.members import current_member, require_access, require_same_origin
from app.payload import EvidenceItem

router = APIRouter()
# Client facing copy, word for word from docs/planning/04_interface.md.
TOO_MANY = "Too many links read just now. Please wait a minute; you can still post."

# One person, one browser: 30 pages in ten minutes. The whole site: 600 a day, 20 a minute.
person_limit = KeyedLimit(30, 600)
site_minute = MinuteBucket(capacity=20, period=60.0)
site_daily = DailyLimit(capacity=600)


class CheckRequest(BaseModel):
    url: str = Field(max_length=2000)
    evidence: str = Field(default="", max_length=300)
    about: str = Field(max_length=300)
    text: str = Field(default="", max_length=4000)
    stance: str = "supports"


def reader_key(request: Request) -> str:
    member = current_member(request)
    if member is not None:
        return member.key
    seen = request.cookies.get("oci_anon") or (request.client.host if request.client else "")
    return "browser:" + hashlib.sha256(seen.encode("utf-8")).hexdigest()[:16]


def _added(first: dict | None, second: dict | None) -> dict | None:
    if not first or not second:
        return first or second
    return {k: first.get(k, 0) + second.get(k, 0) for k in ("prompt_tokens", "completion_tokens")}


def read_link(url: str, evidence: str, about: str, statement: str, settings, *, fetcher=fetch, **kwargs) -> check.Check:
    """check.check_evidence, plus what PDFs need (03_schema.md, revision round: PDFs and arXiv papers).
    An arXiv abstract that does not settle it has its full paper read too, and that reading stands for the
    link; an arXiv paper is primary research; a PDF with no text answers notext, which is never kept."""
    reasons = []

    def reading(link, **more):
        page = fetcher(link, **more)
        reasons.append(page.reason)
        return page

    result = check.check_evidence(url, evidence, about, statement, settings, fetcher=reading, **kwargs)
    if not reasons:  # no reading service, or a reading already in the cache
        return result
    paper = fetch_pdf.arxiv_paper(url)
    if paper and result.verdict in ("unclear", "unread"):
        full = check.check_evidence(paper, evidence, about, statement, settings, fetcher=reading, **kwargs)
        if full.verdict in check.VERDICTS:
            # The abstract page's date is the paper's; the PDF's own is when arXiv last made the file.
            dated = (result.source or {}).get("published")
            result = replace(full, url=result.url, usage=_added(result.usage, full.usage))
            if dated and result.source:
                result = replace(result, source={**result.source, "published": dated})
    if result.verdict == "unread" and reasons[-1] == "no_text":
        result = replace(result, verdict="notext")
    if fetch_pdf.is_arxiv_paper(url) and result.source:
        result = replace(result, source={**result.source, "type": "research", "primary": True})
    check.cache.put(check.cache_key(url, about, statement), result)
    return result


def answer(result: check.Check) -> JSONResponse:
    body = result.as_json()
    body["line"] = check.source_words(result.source)
    return JSONResponse(body)


@router.post("/api/check-evidence", dependencies=[Depends(require_access), Depends(require_same_origin)])
def check_evidence(request: Request, data: CheckRequest) -> Response:
    settings = config.get_settings()
    if not settings.evidence_check_enabled:
        return JSONResponse({"message": "Not found"}, status_code=404)
    url = EvidenceItem(url=data.url).url
    if not url or not data.about.strip():
        return JSONResponse({"verdict": "unchecked", "url": data.url, "line": None})
    if not settings.llm_api_key:
        return answer(check.Check("unchecked", url))
    cached = check.cache.get(check.cache_key(url, data.about, data.text))
    if cached is not None:
        return answer(cached)
    if not person_limit.take(reader_key(request)) or not site_daily.take(site_minute):
        return JSONResponse({"message": TOO_MANY}, status_code=429)
    candidates = graph.candidates()
    result = read_link(url, data.evidence, data.about, data.text, settings,
                                  writer_says=data.stance, candidates=candidates,
                                  request_id=getattr(request.state, "request_id", None))
    return answer(result)
