"""Source confidence on the issue page (04_interface.md, "Source confidence, on the issue page";
03_schema.md, Q39 and the disagreement rule). Used only with EVIDENCE_CHECK_ENABLED set. No Cypher."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from app.check import source_words

AGAINST = "The page was read as arguing against this."
FOR = "The page was read as supporting this."
NUMBERS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
OTHER_SIDE = {"SUPPORTS": "REFUTES", "REFUTES": "SUPPORTS"}
# Under "Supported by" a reading of refutes went the other way, and the other way round.
DIFFERS = {"SUPPORTS": ("refutes", AGAINST), "REFUTES": ("supports", FOR)}


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
            "published": row.get("source_published")}


def lines(rows: list[dict[str, Any]], today: date | None = None) -> dict[tuple, dict[str, Any] | None]:
    """Q39's rows (one per evidence edge) to one entry per (target kind, target key, evidence key, side):
    {"words": the source confidence line or None, "differs": the disagreement line or None}, or None
    when there is neither."""
    sides: dict[tuple, dict[str, set[str]]] = defaultdict(lambda: {"SUPPORTS": set(), "REFUTES": set()})
    checks: dict[tuple, set] = defaultdict(set)
    sources: dict[str, dict[str, Any] | None] = {}
    for row in rows:
        target = (row["target_kind"], row["target_key"])
        sides[target][row["stance"]].add(row["evidence_key"])
        checks[target + (row["evidence_key"], row["stance"])].add(row.get("check"))
        sources.setdefault(row["evidence_key"], _source(row))
    out: dict[tuple, dict[str, Any] | None] = {}
    for key, seen in checks.items():
        kind, target_key, evidence_key, stance = key
        on_target = sides[(kind, target_key)]
        same = len(on_target[stance] - {evidence_key})
        other = len(on_target[OTHER_SIDE[stance]] - {evidence_key})
        parts = [source_words(sources.get(evidence_key), today=today), agreement_words(same, other)]
        words = " ".join(part for part in parts if part) or None
        reading, line = DIFFERS[stance]
        differs = line if reading in seen else None
        out[key] = {"words": words, "differs": differs} if words or differs else None
    return out


def annotate(issue_key: str, evidence: list[dict[str, Any]], solutions: list[dict[str, Any]],
             rows: list[dict[str, Any]], today: date | None = None) -> None:
    """Put `confidence` and `differs` on each evidence item of the issue page, in place."""
    found = lines(rows, today=today)

    def mark(kind: str, target_key: str, items: list[dict[str, Any]]) -> None:
        for item in items:
            entry = found.get((kind, target_key, item["key"], item["stance"])) or {}
            item["confidence"], item["differs"] = entry.get("words"), entry.get("differs")

    mark("issue", issue_key, evidence)
    for solution in solutions:
        mark("solution", solution["key"], solution["evidence"])
