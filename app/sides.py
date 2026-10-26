"""Both sides of one evidence row (GitHub issue 29; 03_schema.md, "Revision round: the page's side and the
writer's side"). No Cypher, no I/O.

When the page behind a row's link was read, by this site, as supporting or refuting what the row is about,
and the writer chose the other side, the post stores two pieces of evidence: the page on the side it was
read as taking, and the writer's own statement, with no link, on the writer's side, tied to the page by
`answers` on its edge. A partly agrees, unclear or unread reading, a row with no kept reading, and every
post written with EVIDENCE_CHECK_ENABLED unset stay one piece of evidence on the writer's side.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from app.text import clean_name, make_key

# Only a reading that takes a side splits a row; partly agrees counts as agreeing but is never split.
SPLITS = ("supports", "refutes")
# The statement's name when the reading kept none of the writer's own sentence about the page.
FALLBACK = "Statement on {name}"


def page_side(row: dict[str, Any], kept: dict[str, Any] | None) -> str | None:
    """The side the page was read as taking, when it is not the writer's; else None."""
    verdict = (kept or {}).get("check")
    if not row.get("url") or verdict not in SPLITS or verdict == row.get("stance"):
        return None
    return verdict


def _name(claim: str | None, source_name: str, taken: set[str]) -> tuple[str, str] | None:
    """The statement's name and key: the writer's own sentence about the page when it is a name of its
    own, else "Statement on <the page's name>"; None when neither is free."""
    for name in (clean_name(claim or ""), clean_name(FALLBACK.format(name=source_name))):
        key = make_key(name) if name else None
        if key and key not in taken:
            return name, key
    return None


def attach(evidence: list[dict[str, Any]], checks: dict[str, dict[str, Any]] | None,
           linked: Callable[[], Iterable[str]] = lambda: ()) -> dict[str, dict[str, Any]] | None:
    """Put `statement` on each kept check whose row splits: {"key", "name", "stance" (the writer's),
    "page" (the page's side)}, in place, and return `checks`. `evidence` are the resolved rows; `linked`
    gives the keys of evidence the record holds with a link (asked only when a row splits), which a
    statement never takes, nor the key of any row on this card or of an earlier statement."""
    if not checks:
        return checks
    splitting = [(row, side) for row in evidence if (side := page_side(row, checks.get(row["key"])))]
    if not splitting:
        return checks
    taken = {row["key"] for row in evidence} | set(linked())
    for row, side in splitting:
        named = _name(checks[row["key"]].get("check_claim"), row["name"], taken)
        if named is None:
            continue  # no free name: the row stays one piece of evidence on the writer's side
        taken.add(named[1])
        checks[row["key"]]["statement"] = {"key": named[1], "name": named[0], "stance": row["stance"], "page": side}
    return checks


def statements(checks: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """The statement of each row that splits, keyed by the page's evidence key."""
    return {key: row["statement"] for key, row in (checks or {}).items() if row.get("statement")}
