"""What the reading found beside what its writer posted, for the back room's "Readings changed by their writers"
(03_schema.md, Post.reading_payload and Q55; 04_interface.md, "Back room additions"); no Cypher, no I/O."""

import json
from typing import Any, Callable

from app import extract as reading
from app.payload import Candidates, CardPayload, ResolvedPayload, resolve_payload

LABELS = {"Issue": "issue", "Solution": "solution", "Evidence": "evidence"}


def reading_payload(extraction_raw: str | None, candidates: Candidates, text: str,
                    resolve: Callable[[CardPayload], ResolvedPayload] | None = None) -> str | None:
    """The reading's card, prepared as /api/extract prepared it and resolved as the post is (`resolve`, for an
    edit; otherwise against `candidates`), as the JSON a post keeps in `payload`. None for no reading, or one
    that cannot be read again."""
    if not extraction_raw:
        return None
    try:
        card = reading.prepared_card(reading.parse_payload(extraction_raw), candidates, text)
    except ValueError:
        return None
    return (resolve(card) if resolve else resolve_payload(card, candidates)).as_json()


def _names(candidates: Candidates, *payloads: dict) -> dict[str, str]:
    names = {}
    for payload in payloads:
        for kind in ("issues", "solutions", "evidence"):
            names.update({row["key"]: row["name"] for row in payload.get(kind, [])})
    names.update({key: item["name"] for key, item in candidates.issues.items()})
    names.update(candidates.solutions)
    names.update(candidates.evidence)
    return names


def lines(payload: dict, names: dict[str, str]) -> set[str]:
    """What a resolved payload adds, one line each, in the display verbs, without the writer's name."""
    name = lambda key: names.get(key, key)
    out = {f"claims {name(row['key'])}" for row in payload.get("issues", [])}
    for row in payload.get("solutions", []):
        if not row.get("stance_only"):
            out.add(f"proposes solution {name(row['key'])} for {name(row['for_issue_key'])}")
        if row.get("stance", "none") != "none":
            out.add(f"{row['stance']}s {name(row['key'])}")
    for row in payload.get("evidence", []):
        link = f" ({row['url']})" if row.get("url") else ""
        out.add(f"submits evidence {name(row['key'])}{link}, which {row['stance']} "
                f"{LABELS.get(row['target_label'], 'issue')} of {name(row['target_key'])}")
    return out


def _day(value: Any) -> str:
    if hasattr(value, "to_native"):
        value = value.to_native()
    return value.strftime("%-d %B %Y") if value else ""


def page_rows(rows: list[dict], candidates: Candidates) -> tuple[list[dict], int]:
    """The posts whose writer changed what the reading found, in the order given (Q55: newest change first), and
    how many readings could not be read again. A post kept before Post.reading_payload existed has its reading
    worked out from extraction_raw against the record as it is now."""
    shown, unreadable = [], 0
    for row in rows:
        found, today = row.get("reading_payload"), not row.get("reading_payload")
        if today:
            found = reading_payload(row.get("extraction_raw"), candidates, row.get("text") or "")
        try:
            before, after = json.loads(found or ""), json.loads(row.get("payload") or "{}")
        except ValueError:
            unreadable += 1
            continue
        names = _names(candidates, before, after)
        found_lines, posted_lines = lines(before, names), lines(after, names)
        if found_lines == posted_lines:
            continue
        shown.append({"id": row["id"], "when": _day(row.get("edited_at") or row.get("created_at")),
                      "name": row.get("display_name") or "Anonymous", "text": row.get("text") or "",
                      "taken_out": sorted(found_lines - posted_lines), "added": sorted(posted_lines - found_lines),
                      "worked_out_today": today})
    return shown, unreadable
