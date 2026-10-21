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
import calendar
from datetime import date, datetime, timezone
from typing import Any, Callable

import httpx

from app.config import Settings
from app.extract import call_model
from app.fetch_page import Page, backup_allowed, backup_fetch, fetch, iso_date
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
(refutes), or does not clearly say either way (unclear). The verdict is about the claim, never
about the writer's statement or the writer's position. First read the claim as something that
can be true or false:
- An issue is often named as a topic, a belief or a claim rather than a sentence ("Flat Earth
  claim", "Belief in astrology", "Vaccine injury theory", "Rising sea levels"). Read it as "the
  belief, claim or problem it names is true or real". Supports means the page says it is true or
  real; refutes means the page says it is false, wrong, disproved or not real. A page that
  disproves a belief refutes an issue named after that belief.
- A solution supports when the page says it would work or should be done, and refutes when the
  page says it would not work or should not be done.
- When you cannot tell which way the claim points, answer unclear.
Rules:
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

    def same_claim(self, url: str, about_key: str) -> list[Check]:
        """Every reading of `url` for the same claim, whatever the statement was when it was read."""
        with self.lock:
            return [value for (u, a, _), value in self.items.items() if u == url and a == about_key]


cache = _Cache()


def cache_key(url: str, about: str, statement: str) -> tuple[str, str, str]:
    digest = hashlib.sha256(" ".join(statement.split()).encode("utf-8")).hexdigest()[:16]
    return url.strip(), (make_key(about) or about.strip().lower()), digest


# Footnote marks like Wikipedia's "[4]", "[a]", "[note 2]" or "[citation needed]": a quote copied without
# them is still on the page.
FOOTNOTE = re.compile(r"\[(?:\d{1,4}|[a-z]|note \d{1,3}|citation needed)\]", re.I)


def flat(text: str) -> str:
    """Lower case, no footnote marks, one kind of quote mark and dash, single spaces: for finding a
    quote on a page."""
    text = FOOTNOTE.sub("", text).lower().translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
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
    # A reference work (an encyclopedia or dictionary page) is kept up to date, so its date is the
    # last update, not the day the page was first written (Wikipedia gives both).
    if kind == "reference" and page.modified:
        published = page.modified
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
                   backup: Callable[..., Page] = backup_fetch,
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
    if backup_allowed(page, settings):
        page = backup(url, settings, about=f"{evidence_name} {about}", request_id=request_id)
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
    quote = " ".join(FOOTNOTE.sub("", quote).split())
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
    key = cache_key(url, about, statement)

    def matches(hit: Check | None) -> bool:
        return hit is not None and hit.verdict == verdict and (hit.quote or None) == (quote or None)

    hit = cache.get(key)
    if matches(hit):
        return hit
    # The writer may tidy the statement after the link was read; the reading was of the same page for
    # the same claim, so it still holds.
    return next((other for other in cache.same_claim(key[0], key[1]) if matches(other)), None)


NO_CHECK = {"check": None, "check_quote": None, "checked_at": None, "source": None}


def _when(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def kept_checks(items: list[Any], evidence: list[dict[str, Any]], statement: str,
                stored: dict[tuple[str, str], dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """For each resolved evidence row (`evidence`, keyed), what its post edge and Evidence node take:
    `check`, `check_quote`, `checked_at` and `source`, or NO_CHECK. `items` are the card's own rows,
    whose `check` is only a claim: it is kept when this process made that reading (confirmed), or,
    for an edited post, when it is the reading the record already holds on this post's edge for the
    same evidence, target and link (`stored`, keyed by evidence key and target key). A kept stored
    reading leaves the source facts alone; they were set when it was made. A reading is only of the
    claim the row was read against, so it is kept only when the row landed on that claim (not on the
    card's first issue as a fallback), and only from the first row of that name, the one resolved."""
    claimed: dict[str | None, Any] = {}
    for item in items:
        claimed.setdefault(make_key(clean_name(item.name)), item)
    out: dict[str, dict[str, Any]] = {}
    for row in evidence:
        out[row["key"]] = dict(NO_CHECK)
        item = claimed.get(row["key"])
        if (item is None or not getattr(item, "check", None) or not row.get("url")
                or make_key(clean_name(item.about or "")) != row["target_key"]):
            continue
        verdict, quote = item.check.get("verdict"), item.check.get("quote") or None
        before = (stored or {}).get((row["key"], row["target_key"]))
        if (before and before.get("url") == row["url"] and before.get("check") == verdict
                and (before.get("check_quote") or None) == quote):
            out[row["key"]] = {"check": verdict, "check_quote": quote,
                               "checked_at": before.get("checked_at"), "source": None}
            continue
        hit = confirmed(row["url"], item.about or "", statement, verdict, quote)
        if hit is not None:
            out[row["key"]] = {"check": hit.verdict, "check_quote": hit.quote, "checked_at": _when(hit.checked_at),
                               "source": hit.source if hit.verdict in ("supports", "refutes", "unclear") else None}
    return out


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


def more_than_five_years(published: str | None, today: date) -> bool:
    """True when the date given ends more than five years before `today`. A year alone counts from
    the end of that year and a month from the end of that month (04_interface.md, John 20 October)."""
    parts = (published or "").split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) >= 2 else 12
        day = int(parts[2]) if len(parts) >= 3 else calendar.monthrange(year, month)[1]
        end = date(year, month, day)
    except (ValueError, IndexError):
        return False
    years_ago = today.year - 5
    limit = date(years_ago, today.month, min(today.day, calendar.monthrange(years_ago, today.month)[1]))
    return end < limit


def source_words(source: dict[str, Any] | None, today: date | None = None) -> str | None:
    """What a page says about itself, in words (04_interface.md, Phase 2, as John approved it):
    'A news report from March 2018. More than five years old. Secondary source.' The date is counted
    against `today` (the day the line is shown). Agreement is added on the issue page."""
    if not source:
        return None
    kind = SOURCE_WORDS.get(source.get("type") or "other", "page")
    article = "An" if kind[0] in "aeiou" else "A"
    date_words = when(source.get("published"))
    first = f"{article} {kind} from {date_words}." if date_words else f"{article} {kind}. Date not given."
    if date_words and more_than_five_years(source.get("published"), today or date.today()):
        first += " More than five years old."
    primary = source.get("primary")
    second = " Primary source." if primary is True else " Secondary source." if primary is False else ""
    return first + second
