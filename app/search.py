"""Keyword search on the Issues page (03_schema.md, Phase 1, Q26 and Q27; GitHub issue 2), and the
looser query that finds what a question asked of the whole record is about (Phase 3)."""

import re
import string
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


# A question is read up to here (the ask box takes 500 characters); the word cap is the same.
QUESTION_CHARS = 500
# Words that say nothing about what a question is about (Phase 3, ask the record).
STOP_WORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing done down during each either else ever every few for
from further get gets got had has have having he her here hers herself him himself his how however i if
in into is it its itself just let like many may me might more most much must my myself no nor not now of
off on once one only or other our ours ourselves out over own per please same say says she should so
some such tell than that the their theirs them themselves then there these they this those through to
too under until up upon us very was we were what whats when where whether which while who whom whose why
will with within without would yet you your yours yourself yourselves
whos hows wheres whens whys theres thats dont doesnt didnt isnt arent wasnt werent cant couldnt wont
wouldnt shouldnt ive im youre theyre weve lets
""".split()) | frozenset(
# Words about the record itself, not about what a question is about: "What reasons do people give for
# opposing solutions?" must not pick the issues whose names say "solutions" (Phase 3 walk, 26 October).
"""
solution solutions issue issues evidence post posts record records people person reason reasons think
thinks thought say said says give given gives opinion opinions view views someone anyone everyone nobody
""".split())
_EDGES = string.punctuation + "“”‘’«»…"


# Endings taken off a word so "opposing" also finds "oppose" and "opposed": the indexes keep words whole.
_ENDINGS = ("ations", "ation", "itions", "ition", "ings", "ing", "ions", "ion", "ers", "er", "ed", "es", "s")


def _stem(word: str) -> str:
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            return word[:-len(ending)]
    return word


def question_query(text: str) -> str | None:
    """A question in sentences: stop words dropped and the rest ORed, each as written or as the start
    of a word (and of the word without a common ending), so a post or name needs only some of the
    words to be found. Punctuation around a word
    is dropped (a question ends in "?"); what remains is escaped as in lucene_query, so nothing typed
    can change what the query means. At most MAX_WORDS terms; None when no word is left."""
    terms: list[str] = []
    for word in text[:QUESTION_CHARS].lower().split():
        word = word.strip(_EDGES)
        # A word of one character ("c" left from "c++") would match every word that starts with it.
        if len(word) < 2 or not _WORDY.search(word) or word.replace("'", "").replace("’", "") in STOP_WORDS:
            continue
        escaped = _SPECIAL.sub(r"\\\1", word)
        stem = _stem(word)
        also = f" {_SPECIAL.sub(r'\\\1', stem)}*" if stem != word else ""
        term = f"({escaped} {escaped}*{also})"
        if term not in terms:
            terms.append(term)
        if len(terms) == MAX_WORDS:
            break
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
