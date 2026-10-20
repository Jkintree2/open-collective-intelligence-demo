"""Phase 2: does the page behind an evidence link say what the writer claims? No Cypher.

One reading per link, separate from the reading of the statement. Guard rails live here, not
in the prompt: a quote that is not on the page turns the verdict into unclear, unknown source
types become other, and suggestions are cleaned like card rows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from app.config import Settings
from app.extract import call_model
from app.fetch_page import Page, fetch, iso_date
from app.payload import Candidates
from app.text import clean_name, make_key

log = logging.getLogger("oci")

VERDICTS = ("supports", "refutes", "unclear")
SOURCE_TYPES = ("news", "research", "government", "reference", "organisation", "blog", "other")
SUGGESTION_KINDS = ("issues", "solutions", "evidence")
MAX_SUGGESTIONS = 3
QUOTE_MAX = 500
REASON_MAX = 300
CACHE_SIZE = 500

SYSTEM_PROMPT = """
You check one piece of evidence for a shared public record of issues, solutions and evidence.

You get JSON with:
- "claim": the issue or solution the evidence is cited about.
- "evidence_name": the short title the writer gave the evidence.
- "statement": what the writer wrote, for context only.
- "writer_says": "supports" or "refutes", how the writer used the evidence. Do not let it sway you.
- "page": the title, description, date and text of the page behind the evidence's link.

Decide, from the page text alone, whether the page supports the claim, argues against it
(refutes), or does not clearly say either way (unclear). Rules:
- Supports or refutes only when a sentence on the page says so directly. Topic overlap is not
  support. A page that reports a view without endorsing it is unclear unless the claim is that
  the view exists.
- When in doubt, answer unclear. Calling a page supporting when it argues against is the worst
  mistake you can make.
- "quote" is one sentence copied exactly, character for character, from page.text, that your
  verdict rests on. No paraphrase, no joining of sentences, no ellipsis. For unclear, give the
  closest sentence or an empty string.
- "reason" is one short plain sentence a member of the public can read. Never mention yourself,
  models, extraction, nodes, edges or graphs. No dashes.

Also describe the source, from the page itself:
- "type": news, research, government, reference, organisation, blog or other.
- "primary": true when the page is the original study, data, record, law or first hand account;
  false when it reports on one; null when you cannot tell.
- "published": the date the page gives for itself as YYYY-MM-DD, YYYY-MM or YYYY, or null.

Finally list what else on the page bears on this conversation and is not already in the claim,
at most three of each, each a short name of under twelve words in the page's own terms:
"issues" (problems), "solutions" (proposed actions) and "evidence" (specific studies, data sets
or reports the page cites). Empty lists are fine and usual.

Answer with one JSON object and nothing else:
{"verdict": "supports" | "refutes" | "unclear",
 "quote": "...",
 "reason": "...",
 "source": {"type": "...", "primary": true | false | null, "published": "..." | null},
 "suggested": {"issues": ["..."], "solutions": ["..."], "evidence": ["..."]}}
""".strip()


@dataclass
class Check:
    """verdict: supports, refutes, unclear (read), unread (page not opened), unsupported (not a
    web page) or unchecked (no reading service, or it failed)."""
    verdict: str
    url: str
    quote: str | None = None
    reason: str | None = None
    source: dict[str, Any] | None = None
    suggested: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    checked_at: str | None = None
    usage: dict[str, Any] | None = None

    def as_json(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "url": self.url, "quote": self.quote, "reason": self.reason,
                "source": self.source, "suggested": self.suggested, "checked_at": self.checked_at}


class _Cache:
    """The last CACHE_SIZE readings, for the life of the process (03_schema.md, Phase 2)."""

    def __init__(self, size: int = CACHE_SIZE) -> None:
        self.size = size
        self.items: OrderedDict[tuple[str, str, str], Check] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return self.items[key]
        return None

    def put(self, key, value: Check) -> None:
        with self.lock:
            self.items[key] = value
            self.items.move_to_end(key)
            while len(self.items) > self.size:
                self.items.popitem(last=False)

    def clear(self) -> None:
        with self.lock:
            self.items.clear()


cache = _Cache()


def cache_key(url: str, about: str, statement: str) -> tuple[str, str, str]:
    digest = hashlib.sha256(" ".join(statement.split()).encode("utf-8")).hexdigest()[:16]
    return url.strip(), (make_key(about) or about.strip().lower()), digest


def flat(text: str) -> str:
    """Lower case, one kind of quote mark and dash, single spaces: for finding a quote on a page."""
    text = text.lower().translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                                                 "–": "-", "—": "-", " ": " "}))
    return " ".join(text.split())


def on_page(quote: str, page: Page) -> bool:
    wanted = flat(quote).strip(" .\"'")
    return len(wanted) >= 12 and wanted in flat(page.text)


def parse_check(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        if start < 0:
            raise ValueError("no json object") from None
        data, _ = json.JSONDecoder().raw_decode(content[start:])
    if not isinstance(data, dict) or data.get("verdict") not in VERDICTS:
        raise ValueError("no verdict")
    return data


def _source(raw: Any, page: Page) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    kind = raw.get("type") if raw.get("type") in SOURCE_TYPES else "other"
    primary = raw.get("primary") if isinstance(raw.get("primary"), bool) else None
    published = page.published or iso_date(raw.get("published") if isinstance(raw.get("published"), str) else None)
    return {"type": kind, "primary": primary, "published": published}


def _suggestions(raw: Any, about: str, evidence_name: str, candidates: Candidates) -> dict[str, list[dict[str, Any]]]:
    raw = raw if isinstance(raw, dict) else {}
    known = {"issues": set(candidates.issues), "solutions": set(candidates.solutions),
             "evidence": set(candidates.evidence)}
    skip = {make_key(about), make_key(evidence_name)}
    out: dict[str, list[dict[str, Any]]] = {}
    for kind in SUGGESTION_KINDS:
        rows, seen = [], set()
        for item in raw.get(kind) or []:
            if not isinstance(item, str):
                continue
            name = clean_name(item)
            key = make_key(name)
            if not key or key in skip or key in seen or len(name) > 160:
                continue
            seen.add(key)
            rows.append({"name": name, "existing": key in known[kind]})
            if len(rows) == MAX_SUGGESTIONS:
                break
        out[kind] = rows
    return out


def build_messages(page: Page, evidence_name: str, about: str, statement: str, writer_says: str) -> list[dict[str, str]]:
    context = {"claim": about, "evidence_name": evidence_name, "statement": statement[:4000],
               "writer_says": writer_says if writer_says in ("supports", "refutes") else "supports",
               "page": {"title": page.title, "description": page.description,
                        "published": page.published, "text": page.text}}
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]


def check_evidence(url: str, evidence_name: str, about: str, statement: str, settings: Settings, *,
                   writer_says: str = "supports", candidates: Candidates | None = None,
                   request_id: str | None = None, fetcher: Callable[..., Page] = fetch,
                   transport: httpx.BaseTransport | None = None) -> Check:
    """Read the page behind `url` and say whether it supports `about`. Never raises for a bad page
    or a bad reply; without a reading service the answer is unchecked and nothing is fetched."""
    url = url.strip()
    if not settings.llm_api_key:
        return Check("unchecked", url)
    key = cache_key(url, about, statement)
    if (hit := cache.get(key)) is not None:
        return hit
    page = fetcher(url, about=f"{evidence_name} {about}", request_id=request_id)
    now = datetime.now(timezone.utc).isoformat()
    if page.status != "ok":
        result = Check("unsupported" if page.status == "unsupported" else "unread", url, checked_at=now)
        cache.put(key, result)
        return result
    reply = call_model(build_messages(page, evidence_name, about, statement, writer_says), settings,
                       request_id=request_id, chars=len(page.text), transport=transport,
                       parse=parse_check, event="check", max_tokens=700)
    if reply is None:
        return Check("unchecked", url)
    log.debug(json.dumps({"event": "check_raw", "request_id": request_id, "raw": reply.extraction_raw}))
    data = reply.payload
    verdict = data["verdict"]
    quote = data.get("quote") if isinstance(data.get("quote"), str) else ""
    quote = " ".join(quote.split())
    if verdict in ("supports", "refutes") and not on_page(quote, page):
        log.info(json.dumps({"event": "check_quote_missing", "request_id": request_id}))
        verdict = "unclear"
    reason = data.get("reason") if isinstance(data.get("reason"), str) else ""
    result = Check(
        verdict, url,
        quote=quote[:QUOTE_MAX] if verdict in ("supports", "refutes") else None,
        reason=re.sub(r"\s+", " ", reason).strip()[:REASON_MAX] or None,
        source=_source(data.get("source"), page),
        suggested=_suggestions(data.get("suggested"), about, evidence_name, candidates or Candidates.empty()),
        checked_at=now,
        usage=reply.usage,
    )
    cache.put(key, result)
    return result


def confirmed(url: str, about: str, statement: str, verdict: str | None, quote: str | None) -> Check | None:
    """The cached reading behind a card row's check, when it matches what the card sent; else None.
    The write path keeps a row's check only through this (03_schema.md, Phase 2)."""
    if not url or verdict not in VERDICTS + ("unread",):
        return None
    hit = cache.get(cache_key(url, about, statement))
    if hit is None or hit.verdict != verdict or (hit.quote or None) != (quote or None):
        return None
    return hit


SOURCE_WORDS = {"news": "news report", "research": "research paper", "government": "government source",
                "reference": "reference work", "organisation": "organisation's page", "blog": "blog post", "other": "page"}
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December")


def when(published: str | None) -> str | None:
    """'March 2024', '2024', or None, from YYYY-MM-DD, YYYY-MM or YYYY."""
    if not published:
        return None
    parts = published.split("-")
    if len(parts) >= 2 and parts[1].isdigit() and 1 <= int(parts[1]) <= 12:
        return f"{MONTHS[int(parts[1]) - 1]} {parts[0]}"
    return parts[0]


def source_words(source: dict[str, Any] | None) -> str | None:
    """What a page says about itself, in words (04_interface.md, Phase 2; draft copy for John):
    'A news report from March 2024. Secondary source.' Agreement is added on the issue page."""
    if not source:
        return None
    kind = SOURCE_WORDS.get(source.get("type") or "other", "page")
    article = "An" if kind[0] in "aeiou" else "A"
    date = when(source.get("published"))
    first = f"{article} {kind} from {date}." if date else f"{article} {kind}. Date not given."
    primary = source.get("primary")
    second = " Primary source." if primary is True else " Secondary source." if primary is False else ""
    return first + second
