"""v0.3, one box for Write and Ask on the Home page, behind HOME_ENABLED (off, preview or on)."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import Request

from app import config
from app.graph_questions import QUESTION_MAX

Kind = Literal["statement", "question", "unsure"]

# How a text starts when it asks the site something (decision D2: rules, no model call).
WH_WORDS = frozenset({"how", "what", "why", "who", "whom", "whose", "where", "when", "which"})
AUX_WORDS = frozenset({"is", "are", "am", "was", "were", "does", "do", "did", "can", "could", "should", "would",
                       "will", "has", "have", "had", "may", "might", "must", "shall", "isn't", "aren't", "doesn't",
                       "don't", "didn't", "can't", "couldn't", "shouldn't", "wouldn't", "won't", "hasn't", "haven't"})
ASKING_WORDS = frozenset({"explain", "summarize", "summarise", "list", "describe"})
ASKING_FOR_ME = frozenset({"tell", "show", "give"})  # a question only with "me" or "us" after it
QUESTION_OPENERS = WH_WORDS | AUX_WORDS | ASKING_WORDS | ASKING_FOR_ME
FOLLOW_UPS = frozenset({"more", "more please", "tell me more", "say more", "go on", "keep going", "continue", "and",
                        "and then", "what else", "why", "why not", "how so"})
# "What we need is ..." and "How we treat ..." start like questions and read as claims.
SUBJECTS = frozenset({"i", "we", "you", "they", "he", "she", "it", "people", "this", "that", "these", "those"})
LONG_UNMARKED = 20  # words: a question-shaped line longer than this, with no mark, may be a statement
LEADING = frozenset({"please", "and", "but", "so"})
# A period after these does not end a sentence ("St. Louis"), nor after a single letter ("J. Smith").
ABBREVIATIONS = frozenset({"st", "mr", "mrs", "ms", "dr", "prof", "vs", "etc", "jr", "sr", "mt", "u.s", "u.k",
                           "u.n", "e.g", "i.e"})
_SENTENCE_END = re.compile(r"(?<=[.?!])[\"'\u201d\u2019)\]]*\s+")
_WORDS = re.compile(r"[a-z0-9]+(?:['\u2019][a-z]+)?")
_CLOSERS = "\"'\u201d\u2019)] "


def home_on(request: Request) -> bool:
    """Whether this reader gets the Home page: every signed-in member with "on", only the members listed in
    HOME_PREVIEW with "preview", nobody with "off". Signed out, and on the passphrase site (accounts off), never.
    It reads only the member require_access (or the About page) already found, never the database, so an error or
    asleep page that draws the menu cannot fail on it."""
    settings = config.get_settings()
    if settings.home_enabled not in ("preview", "on") or not settings.accounts_enabled:
        return False
    member = getattr(request.state, "member", None)
    if member is None:
        return False
    return settings.home_enabled == "on" or member.email.strip().lower() in settings.home_preview


def _sentences(text: str) -> list[str]:
    """The text cut at each line break, and after each . ? or ! that a space follows, except after an abbreviation
    or a single letter. Each line's spaces are collapsed."""
    out = []
    for line in text.splitlines():
        line, start = " ".join(line.split()), 0
        for end in _SENTENCE_END.finditer(line):
            piece = line[start:end.start()]
            last = piece.rstrip(".?!").rsplit(None, 1)[-1].lower() if piece.strip(" .?!") else ""
            if piece.endswith(".") and (last in ABBREVIATIONS or len(last) == 1):
                continue
            out.append(line[start:end.end()].strip())
            start = end.end()
        out.append(line[start:].strip())
    return [sentence for sentence in out if sentence]


def _opener(word: str) -> tuple[str, bool]:
    """The word with a contraction's "s" taken off ("what's", "whats", "who’s" give what, who), and whether one was."""
    if word.endswith("'s") and word[:-2] in WH_WORDS:
        return word[:-2], True
    if word.endswith("s") and word[:-1] in WH_WORDS and word not in WH_WORDS:
        return word[:-1], True
    return word, False


def _sentence_kind(sentence: str, alone: bool) -> str:
    """question, claim or unsure, for one sentence. `alone`: the whole text is this sentence. A sentence the writer
    ended with a period or ! among others is theirs to call a claim; one with no mark at all (the last, or one cut
    by a line break) is judged by its words. A question that runs long or says "because" with no mark may be a
    statement: unsure, since a question that is answered is listed for everyone."""
    bare = sentence.rstrip(_CLOSERS)
    if bare.endswith("?"):
        return "question"
    words = _WORDS.findall(bare.lower().replace("\u2019", "'"))
    if " ".join(words) in FOLLOW_UPS:
        return "question"
    while len(words) > 1 and words[0] in LEADING:
        words = words[1:]
    if not words:
        return "claim"
    (first, contracted), second = _opener(words[0]), words[1] if len(words) > 1 else ""
    ended = bare.endswith((".", "!"))
    if first in ASKING_WORDS:
        return "question"
    if first in ASKING_FOR_ME:
        return "question" if second in ("me", "us") else "unsure" if alone else "claim"
    if first not in WH_WORDS and first not in AUX_WORDS:
        return "claim"
    if first in ("do", "don't") and (second == "not" or first == "don't" and second not in SUBJECTS):
        return "claim"  # "Do not build ...": an instruction to people
    if ended:
        return "unsure" if alone else "claim"
    if first in WH_WORDS and second in SUBJECTS and not contracted:
        return "unsure"  # "What we need is ...", "How we treat ..."
    if len(words) > LONG_UNMARKED or "because" in words:
        return "unsure"
    return "question"


def kind_of(text: str) -> Kind:
    """statement, question or unsure, by rules (decision D2). The final period or question mark is not always
    there (John, 4 November). Over QUESTION_MAX characters a text is never a question, since Ask would refuse it:
    unsure when it ends with a question mark, so the writer chooses, else a statement."""
    flat = " ".join(text.split())
    if not flat:
        return "statement"
    if len(flat) > QUESTION_MAX:
        return "unsure" if flat.rstrip(_CLOSERS).endswith("?") else "statement"
    sentences = _sentences(text)
    kinds = {_sentence_kind(sentence, len(sentences) == 1) for sentence in sentences}
    if kinds == {"question"}:
        return "question"
    if kinds == {"claim"}:
        return "statement"
    return "unsure"
