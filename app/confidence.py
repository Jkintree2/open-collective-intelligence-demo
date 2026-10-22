"""Source confidence on the issue page (04_interface.md, "Source confidence, on the issue page";
03_schema.md, Q39 and the disagreement rule). Used only with EVIDENCE_CHECK_ENABLED set. No Cypher."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from app.check import PASTED, QUOTED, source_words
from app.fetch_video import is_video

# The disagreement line in John's words (revision round, 22 October 2026).
AGAINST = "The page was read as contradicting this."
FOR = "The page was read as agreeing with this."
PARTLY_FOR = "The page was read as partly agreeing with this."
WORDS = {"supports": "Agrees", "partly": "Partly agrees", "refutes": "Contradicts"}
NO_SOURCE = "No source given."
PERSONAL = "From personal experience."
NUMBERS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
OTHER_SIDE = {"SUPPORTS": "REFUTES", "REFUTES": "SUPPORTS"}



def _count(n: int) -> str:
    return NUMBERS[n - 1] if n <= len(NUMBERS) else str(n)


def agreement_words(same: int, other: int) -> str | None:
    """'Two other pieces of evidence here say the same; one disagrees.', or None when both are none."""
    if not same and not other:
        return None
    first, count = (same, "says the same" if same == 1 else "say the same") if same else \
        (other, "disagrees" if other == 1 else "disagree")
    noun = "other piece of evidence here" if first == 1 else "other pieces of evidence here"
    words = f"{_count(first)} {noun} {count}"
    if same and other:
        words += f"; {_count(other)} {'disagrees' if other == 1 else 'disagree'}"
    return words[0].upper() + words[1:] + "."


def _source(row: dict[str, Any]) -> dict[str, Any] | None:
    if not row.get("source_known"):
        return None
    return {"type": row.get("source_type"), "primary": row.get("source_primary"),
            "published": row.get("source_published"), "cites": row.get("source_cites")}


def differs(stance: str, seen: set) -> str | None:
    """Under "Supported by" a contradicts reading went the other way; under "Refuted by" an agrees or
    partly agrees one did (partly agrees counts as agreeing)."""
    if stance == "SUPPORTS":
        return AGAINST if "refutes" in seen else None
    return FOR if "supports" in seen else PARTLY_FOR if "partly" in seen else None


def reading(row: dict[str, Any]) -> dict[str, Any] | None:
    """One statement's reading of the page, for showing under the evidence: John's word, the writer's
    sentence, the page's, and for partly agrees what the page does not say. Only readings that rest on
    a quote are shown."""
    if row.get("check") not in QUOTED or not row.get("check_quote"):
        return None
    # A video's sentence says where it is; one from a pasted transcript says it rests on the writer's paste.
    pasted, at = bool(row.get("check_pasted")), row.get("check_quote_at")
    said = ("The transcript says" if pasted else "The video says" if at else "The page says") + (f" at {at}" if at else "")
    return {"word": WORDS[row["check"]], "claim": row.get("check_claim"), "quote": row["check_quote"],
            "said": said, "pasted": PASTED if pasted else None,
            "reason": row.get("check_reason") if row["check"] == "partly" else None}


def lines(rows: list[dict[str, Any]], today: date | None = None,
          videos: set[str] | None = None) -> dict[tuple, dict[str, Any] | None]:
    """Q39's rows (one per evidence edge) to one entry per (target kind, target key, evidence key, side):
    {"words": the source confidence line or None, "differs": the disagreement line or None, "readings":
    each distinct reading that rests on a quote, "personal": whether any statement ticked personal
    experience}, or None when there is none of these."""
    sides: dict[tuple, dict[str, set[str]]] = defaultdict(lambda: {"SUPPORTS": set(), "REFUTES": set()})
    checks: dict[tuple, set] = defaultdict(set)
    readings: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    personal: set[tuple] = set()
    sources: dict[str, dict[str, Any] | None] = {}
    for row in rows:
        target = (row["target_kind"], row["target_key"])
        key = target + (row["evidence_key"], row["stance"])
        sides[target][row["stance"]].add(row["evidence_key"])
        checks[key].add(row.get("check"))
        if (found := reading(row)) is not None and found not in readings[key]:
            readings[key].append(found)
        if row.get("personal"):
            personal.add(key)
        sources.setdefault(row["evidence_key"], _source(row))
    out: dict[tuple, dict[str, Any] | None] = {}
    for key, seen in checks.items():
        kind, target_key, evidence_key, stance = key
        on_target = sides[(kind, target_key)]
        same = len(on_target[stance] - {evidence_key})
        other = len(on_target[OTHER_SIDE[stance]] - {evidence_key})
        parts = [source_words(sources.get(evidence_key), today=today, video=evidence_key in (videos or set())),
                 agreement_words(same, other)]
        words = " ".join(part for part in parts if part) or None
        entry = {"words": words, "differs": differs(stance, seen), "readings": readings[key],
                 "personal": key in personal}
        out[key] = entry if any(entry.values()) else None
    return out


def annotate(issue_key: str, evidence: list[dict[str, Any]], solutions: list[dict[str, Any]],
             rows: list[dict[str, Any]], today: date | None = None) -> None:
    """Put `confidence`, `differs`, `readings` and, for evidence with no link, `source_note` ("No source
    given." or "From personal experience.") on each evidence item of the issue page, in place."""
    items = evidence + [item for solution in solutions for item in solution["evidence"]]
    found = lines(rows, today=today, videos={item["key"] for item in items if is_video(item.get("url"))})

    def mark(kind: str, target_key: str, items: list[dict[str, Any]]) -> None:
        for item in items:
            entry = found.get((kind, target_key, item["key"], item["stance"])) or {}
            item["confidence"], item["differs"] = entry.get("words"), entry.get("differs")
            item["readings"] = entry.get("readings") or []
            item["source_note"] = None if item.get("url") else PERSONAL if entry.get("personal") else NO_SOURCE

    mark("issue", issue_key, evidence)
    for solution in solutions:
        mark("solution", solution["key"], solution["evidence"])
