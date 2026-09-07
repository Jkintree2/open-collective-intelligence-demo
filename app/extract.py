"""The card payload: pydantic models and the server side rules from docs/planning/05_extraction.md.

Session 2 ships the models and `resolve_payload()` only. The model call arrives in Session 3.
Anything that fails a rule is dropped or corrected, never rejected wholesale.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.text import clean_name, make_key

log = logging.getLogger("oci")

MAX_ISSUES = 3
MAX_SOLUTIONS = 5
MAX_EVIDENCE = 5
SOLUTION_STANCES = ("none", "approve", "oppose")
EVIDENCE_STANCES = ("supports", "refutes")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


class IssueItem(BaseModel):
    name: str = ""
    parent: str | None = None
    existing: bool = False

    @field_validator("name", "parent", mode="before")
    @classmethod
    def _strings(cls, value: Any) -> str | None:
        return _text(value) or None if value is not None else None


class SolutionItem(BaseModel):
    name: str = ""
    for_issue: str | None = None
    stance: str = "none"

    @field_validator("name", "for_issue", mode="before")
    @classmethod
    def _strings(cls, value: Any) -> str | None:
        return _text(value) or None if value is not None else None

    @field_validator("stance", mode="before")
    @classmethod
    def _stance(cls, value: Any) -> str:
        value = _text(value).lower()
        return value if value in SOLUTION_STANCES else "none"


class EvidenceItem(BaseModel):
    name: str = ""
    url: str | None = None
    stance: str = "supports"
    about: str | None = None

    @field_validator("name", "about", mode="before")
    @classmethod
    def _strings(cls, value: Any) -> str | None:
        return _text(value) or None if value is not None else None

    @field_validator("url", mode="before")
    @classmethod
    def _url(cls, value: Any) -> str | None:
        """Only an http(s) URL survives; anything else becomes null."""
        value = _text(value)
        return value if value.startswith(("http://", "https://")) else None

    @field_validator("stance", mode="before")
    @classmethod
    def _stance(cls, value: Any) -> str:
        value = _text(value).lower()
        return value if value in EVIDENCE_STANCES else "supports"


class CardPayload(BaseModel):
    language_ok: bool = True
    found: bool = True
    issues: list[IssueItem] = Field(default_factory=list)
    solutions: list[SolutionItem] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    note: str = ""

    @field_validator("issues", "solutions", "evidence", mode="before")
    @classmethod
    def _drop_junk_rows(cls, value: Any) -> list[Any]:
        if not isinstance(value, list):
            return []
        return [row for row in value if isinstance(row, dict)]

    @field_validator("note", mode="before")
    @classmethod
    def _note(cls, value: Any) -> str:
        return _text(value)[:300]


@dataclass(frozen=True)
class Candidates:
    """What already exists in the record, keyed. Issues map to `{"name", "parent_key"}`."""

    issues: dict[str, dict[str, Any]] = field(default_factory=dict)
    solutions: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "Candidates":
        return cls()


@dataclass
class ResolvedPayload:
    """Keys computed, references resolved, ready for `graph.merge_post()`."""

    issues: list[dict[str, Any]] = field(default_factory=list)
    solutions: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.issues or self.solutions or self.evidence)

    def as_json(self) -> str:
        return json.dumps(
            {"issues": self.issues, "solutions": self.solutions, "evidence": self.evidence},
            ensure_ascii=False,
        )


def _keyed(name: str | None) -> tuple[str | None, str]:
    cleaned = clean_name(name or "")
    return make_key(cleaned), cleaned


def resolve_payload(payload: CardPayload, candidates: Candidates) -> ResolvedPayload:
    """Apply the rules under "Rules applied in Python before the transaction" in 03_schema.md."""
    out = ResolvedPayload()

    # Issues: cleaned, keyed, capped, de-duplicated, parents resolved.
    issue_keys: dict[str, dict[str, Any]] = {}
    for item in payload.issues:
        key, name = _keyed(item.name)
        if key is None:
            out.dropped.append(f"issue {item.name!r}")
            continue
        if key in issue_keys:
            continue
        if len(issue_keys) >= MAX_ISSUES:
            out.dropped.append(f"issue {name!r} over the limit of {MAX_ISSUES}")
            continue
        existing = key in candidates.issues
        issue_keys[key] = {
            "key": key,
            "name": candidates.issues[key]["name"] if existing else name,
            "parent_key": None,
            "parent_requested": item.parent,
            "existing": existing,
        }
    for row in issue_keys.values():
        row["parent_key"] = _resolve_parent(row, issue_keys, candidates, out)
        del row["parent_requested"]
    out.issues = list(issue_keys.values())
    first_issue = out.issues[0]["key"] if out.issues else None

    # Solutions: for_issue must be in the payload or the record, else the first issue.
    seen: set[str] = set()
    for item in payload.solutions:
        key, name = _keyed(item.name)
        if key is None:
            out.dropped.append(f"solution {item.name!r}")
            continue
        if key in seen:
            continue
        if len(out.solutions) >= MAX_SOLUTIONS:
            out.dropped.append(f"solution {name!r} over the limit of {MAX_SOLUTIONS}")
            continue
        for_key, _ = _keyed(item.for_issue)
        if for_key not in issue_keys and for_key not in candidates.issues:
            for_key = first_issue
        if for_key is None:
            out.dropped.append(f"solution {name!r} names no issue")
            continue
        seen.add(key)
        out.solutions.append(
            {
                "key": key,
                "name": candidates.solutions.get(key, name),
                "for_issue_key": for_key,
                "stance": item.stance,
                "existing": key in candidates.solutions,
            }
        )
    solution_keys = {row["key"] for row in out.solutions}

    # Evidence: the target is an issue or solution from the payload, or anything in the record.
    seen = set()
    for item in payload.evidence:
        key, name = _keyed(item.name)
        if key is None:
            out.dropped.append(f"evidence {item.name!r}")
            continue
        if key in seen:
            continue
        if len(out.evidence) >= MAX_EVIDENCE:
            out.dropped.append(f"evidence {name!r} over the limit of {MAX_EVIDENCE}")
            continue
        target = _resolve_target(item.about, issue_keys, solution_keys, candidates, key)
        if target is None:
            if first_issue is None:
                out.dropped.append(f"evidence {name!r} has nothing to be about")
                continue
            target = ("Issue", first_issue)
        seen.add(key)
        out.evidence.append(
            {
                "key": key,
                "name": candidates.evidence.get(key, name),
                "url": item.url,
                "stance": item.stance,
                "target_label": target[0],
                "target_key": target[1],
                "existing": key in candidates.evidence,
            }
        )
    if out.dropped:
        log.info(json.dumps({"event": "payload_dropped", "items": out.dropped}))
    return out


def _resolve_parent(
    row: dict[str, Any],
    issue_keys: dict[str, dict[str, Any]],
    candidates: Candidates,
    out: ResolvedPayload,
) -> str | None:
    parent_key, _ = _keyed(row["parent_requested"])
    if parent_key is None or parent_key == row["key"]:
        return None
    if parent_key in issue_keys:
        # A parent named in the same payload is top level by construction.
        return parent_key
    known = candidates.issues.get(parent_key)
    if known is None:
        out.dropped.append(f"parent {row['parent_requested']!r} of {row['name']!r} does not exist")
        return None
    if known.get("parent_key"):
        # A sub-issue cannot be a parent: use its own parent instead (M2).
        out.dropped.append(f"parent {row['parent_requested']!r} is a sub-issue; used its parent")
        return known["parent_key"]
    return parent_key


def _resolve_target(
    about: str | None,
    issue_keys: dict[str, dict[str, Any]],
    solution_keys: set[str],
    candidates: Candidates,
    own_key: str,
) -> tuple[str, str] | None:
    key, _ = _keyed(about)
    if key is None:
        return None
    if key in issue_keys or key in candidates.issues:
        return ("Issue", key)
    if key in solution_keys or key in candidates.solutions:
        return ("Solution", key)
    if key in candidates.evidence and key != own_key:
        return ("Evidence", key)
    return None
