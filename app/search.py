"""Keyword search on the Issues page (03_schema.md, Phase 1, Q26 and Q27; GitHub issue 2).
Search by meaning and event dates are Phase 3."""

import re
from urllib.parse import quote

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
