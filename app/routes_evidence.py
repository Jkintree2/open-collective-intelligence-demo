"""Phase 2: POST /api/check-evidence reads the page behind one evidence link on the card."""

from __future__ import annotations

import hashlib
from dataclasses import replace

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app import check, config, fetch_pdf, fetch_video, graph
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
    # A YouTube video's transcript, pasted by the writer when its captions could not be read; never kept.
    transcript: str = Field(default="", max_length=fetch_video.MAX_TRANSCRIPT)


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


def read_link(url: str, evidence: str, about: str, statement: str, settings, *, fetcher=fetch,
              transcript: str | None = None, **kwargs) -> check.Check:
    """check.check_evidence, plus what PDFs need (03_schema.md, revision round: PDFs and arXiv papers).
    An arXiv abstract read as unclear, unread or partly has its full paper read too: after unclear or unread
    the paper's reading stands; after partly only a paper reading that rests on a quote (agrees, partly agrees,
    contradicts) replaces it. An arXiv paper is primary research; a PDF with no text answers notext, which is
    never kept. A YouTube video (revision round: YouTube videos) is read from its captions, or from `transcript`,
    the writer's paste, read afresh; one that cannot be read answers nocaptions, never kept."""
    reasons, pages = [], []
    video = fetch_video.is_video(url)
    pasted = bool(video and transcript and transcript.strip())

    def reading(link, **more):
        page = fetcher(link, **more, **({"transcript": transcript} if pasted else {}))
        reasons.append(page.reason)
        pages.append(page)
        return page

    result = check.check_evidence(url, evidence, about, statement, settings, fetcher=reading,
                                  **({"fresh": True} if pasted else {}), **kwargs)
    if not reasons:  # no reading service, or a reading already in the cache
        return result
    if video:
        if result.verdict == "unread":
            result = replace(result, verdict="nocaptions")
        else:
            result = replace(result, source=fetch_video.channel_source(result.source), pasted=pasted,
                             quote_at=fetch_video.quote_time(result.quote, getattr(pages[-1], "segments", [])))
        check.cache.put(check.cache_key(url, about, statement), result)
        return result
    paper = fetch_pdf.arxiv_paper(url)
    # A partly agrees from an abstract is often only what a summary leaves out (Eston, 22 October 2026), so the
    # paper is read for it too; it keeps its place unless the paper gives a reading that rests on a quote.
    if paper and result.verdict in ("unclear", "unread", "partly"):
        full = check.check_evidence(paper, evidence, about, statement, settings, fetcher=reading, **kwargs)
        both = _added(result.usage, full.usage)
        if full.verdict in (check.QUOTED if result.verdict == "partly" else check.VERDICTS):
            # The abstract page's date is the paper's; the PDF's own is when arXiv last made the file.
            dated = (result.source or {}).get("published")
            result = replace(full, url=result.url, usage=both)
            if dated and result.source:
                result = replace(result, source={**result.source, "published": dated})
        else:
            result = replace(result, usage=both)
    if result.verdict == "unread" and reasons[-1] == "no_text":
        result = replace(result, verdict="notext")
    if fetch_pdf.is_arxiv_paper(url) and result.source:
        result = replace(result, source={**result.source, "type": "research", "primary": True})
    check.cache.put(check.cache_key(url, about, statement), result)
    return result


def answer(result: check.Check) -> JSONResponse:
    body = result.as_json()
    body["video"] = fetch_video.is_video(result.url)
    body["line"] = check.source_words(result.source, video=body["video"], pasted=result.pasted)
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
    # A transcript counts only for a video link, and is read afresh: the reading before it found no captions.
    transcript = data.transcript if data.transcript.strip() and fetch_video.is_video(url) else None
    cached = None if transcript else check.cache.get(check.cache_key(url, data.about, data.text))
    if cached is not None:
        return answer(cached)
    if not person_limit.take(reader_key(request)) or not site_daily.take(site_minute):
        return JSONResponse({"message": TOO_MANY}, status_code=429)
    candidates = graph.candidates()
    result = read_link(url, data.evidence, data.about, data.text, settings, transcript=transcript,
                       writer_says=data.stance, candidates=candidates,
                       request_id=getattr(request.state, "request_id", None))
    return answer(result)
