"""Text rules from docs/planning/03_schema.md: keys, display names and relative times."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

ARTICLES = ("the", "a", "an")
NAME_MAX = 300
TRAILING_PUNCTUATION = ".,;:!?"
_NOT_ALPHANUMERIC = re.compile(r"[\W_]+")


def normalise(s: str) -> str:
    """NFKC, lowercase, runs of non alphanumerics to one space, trimmed."""
    s = unicodedata.normalize("NFKC", s).lower()
    return _NOT_ALPHANUMERIC.sub(" ", s).strip()


def _strip_leading_article(s: str) -> str:
    """Drop a leading the/a/an only when a space follows it (or it is the whole string)."""
    for article in ARTICLES:
        if s == article:
            return ""
        if s.startswith(article + " "):
            return s[len(article) + 1 :]
    return s


def make_key(s: str) -> str | None:
    """The node key for a name, or None when the key would be shorter than two characters.

    The article check runs on the lowercased text before punctuation is collapsed, so
    "A/B testing" keeps its A while "The need for ..." loses its "the".
    """
    lowered = unicodedata.normalize("NFKC", s).lower().strip()
    key = normalise(_strip_leading_article(lowered))
    return key if len(key) >= 2 else None


def clean_name(s: str) -> str:
    """The display form of a name: newlines to spaces, trimmed, capped at 300, first letter
    upper cased only when it is lower case and the second is not upper case, trailing
    punctuation removed."""
    name = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    name = name[:NAME_MAX].rstrip(TRAILING_PUNCTUATION).strip()
    if name and name[0].islower() and not (len(name) > 1 and name[1].isupper()):
        name = name[0].upper() + name[1:]
    return name


def relative_time(then: datetime, now: datetime | None = None) -> str:
    """"just now", "5 minutes ago", "2 hours ago", "3 days ago"."""
    now = now or datetime.now(timezone.utc)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < 60:
        return "just now"
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            count = seconds // size
            return f"{count} {unit}{'' if count == 1 else 's'} ago"
    return "just now"


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def count_line(row: dict) -> str:
    """The count line under an issue, from docs/planning/04_interface.md screen 3."""
    people = _plural(row["people"], "person", "people")
    solutions = _plural(row["solutions"], "solution", "solutions")
    evidence = _plural(row["evidence"], "piece of evidence", "pieces of evidence")
    if row.get("children"):
        claims = f"{row['claims']} claims in total · {_plural(row['own_claims'], 'claim', 'claims')} on the issue itself"
    else:
        claims = _plural(row["claims"], "claim", "claims")
    return f"{people} · {claims} · {solutions} · {evidence}"


# What a piece of evidence speaks to, by the label of its target (John, 23 October 2026).
TARGET_WORDS = {"Issue": "issue of", "Solution": "solution of", "Evidence": "evidence of"}


def sentences(payload, display_name: str, resolved=None) -> list[str]:
    """The card's sentences, in the order of the acceptance examples, in John's words of 23 October
    2026: "proposes solution", "submits evidence", "supports issue of" (or solution of, evidence of).
    An issue already in the record reads "claims about existing issue" (John, 24 October 2026; from 23 to
    24 October its line was left out whenever the card added anything else).
    `resolved` is the card's ResolvedPayload; without it the card is resolved against an empty record."""
    if resolved is None:
        from app.payload import Candidates, resolve_payload  # payload imports this module

        resolved = resolve_payload(payload, Candidates.empty())
    name = clean_name(display_name) or "Anonymous"
    existing = {row["key"] for row in resolved.issues if row.get("existing")}
    kinds = {row["target_key"]: row["target_label"] for row in resolved.evidence}
    claims = [f"{name} claims {'about existing issue ' if make_key(item.name) in existing else ''}{item.name}"
              for item in payload.issues]
    proposed = [item for item in payload.solutions if not item.stance_only]
    rest = [f"{name} proposes solution {item.name}" for item in proposed]
    rest.extend(f"{item.for_issue} has proposed {item.name}" for item in proposed)
    rest.extend(f"{name} {item.stance}s {item.name}" for item in payload.solutions if item.stance != "none")
    rest.extend(f"{name} submits evidence {item.name}" for item in payload.evidence)
    for item in payload.evidence:
        kind = kinds.get(make_key(item.about or "") or "")
        rest.append(f"{item.name} {item.stance} {TARGET_WORDS[kind] + ' ' if kind else ''}{item.about}")
    return claims + rest
