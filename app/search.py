"""Keyword search on the Issues page (03_schema.md, Phase 1, Q26 and Q27; GitHub issue 2).
Search by meaning and event dates are Phase 3."""

import re
from urllib.parse import quote

from app import graph_search

MAX_CHARS = 200
MAX_WORDS = 10
_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')
_WORDY = re.compile(r"\w")


def lucene_query(text: str) -> str | None:
    """Every word must match (X4), as written or as the start of a word. Every special character is
    escaped and the words are lower-cased (Lucene's AND, OR and NOT are upper case), so nothing typed
    can change what the query means. None when there is nothing to look for."""
    terms = []
    for word in text[:MAX_CHARS].lower().split()[:MAX_WORDS]:
        if not _WORDY.search(word):
            continue
        escaped = _SPECIAL.sub(r"\\\1", word)
        terms.append(f"+({escaped} {escaped}*)")
    return " ".join(terms) or None


def issue_href(key: str) -> str:
    return f"/issues/{quote(key, safe='')}"


_GROUPS = {"Issue": "issues", "Solution": "solutions", "Evidence": "evidence"}


def group(name_rows: list[dict]) -> dict[str, list[dict]]:
    """Each result links to its issue page: an issue to itself, a solution to its first issue,
    evidence to the first issue it is about, directly or through a solution."""
    found: dict[str, list[dict]] = {"issues": [], "solutions": [], "evidence": []}
    for row in name_rows:
        if row["label"] == "Issue":
            home = row["key"]
        elif row["label"] == "Solution":
            home = next(iter(row["solution_homes"]), None)
        else:
            home = next(iter(row["evidence_homes"]), None)
        found[_GROUPS[row["label"]]].append({"name": row["name"], "href": issue_href(home) if home else None})
    return found


def run(text: str, decorate) -> dict[str, list]:
    """Everything the results page shows; `decorate` turns post rows into feed posts."""
    query = lucene_query(text)
    if query is None:
        return {"issues": [], "solutions": [], "evidence": [], "posts": []}
    found = group(graph_search.search_names(query))
    found["posts"] = decorate(graph_search.search_posts(query))
    return found
