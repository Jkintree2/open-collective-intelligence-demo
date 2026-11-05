"""v0.3, one box for Write and Ask on the Home page, behind HOME_ENABLED (off, preview or on)."""

from __future__ import annotations

import hashlib
import hmac
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


def mine_name(request: Request) -> str:
    """The name the browser keeps this member's answered questions under, for "My most recent statements and
    questions": a keyed hash of the account, never the key itself, so a shared browser shows each member only their
    own. Empty unless Home is on for this reader, and then nothing is kept at all."""
    if not home_on(request):
        return ""
    secret = config.get_settings().secret_key.encode("utf-8")
    return hmac.new(secret, f"home-mine:{request.state.member.key}".encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _sentences(text: str) -> list[str]:
    """The text cut after each . ? or ! that a space follows, except after an abbreviation or a single letter."""
    out, start = [], 0
    for end in _SENTENCE_END.finditer(text):
        piece = text[start:end.start()]
        last = piece.rstrip(".?!").rsplit(None, 1)[-1].lower() if piece.strip(" .?!") else ""
        if piece.endswith(".") and (last in ABBREVIATIONS or len(last) == 1):
            continue
        out.append(text[start:end.end()].strip())
        start = end.end()
    out.append(text[start:].strip())
    return [sentence for sentence in out if sentence]


def _sentence_kind(sentence: str, alone: bool, last: bool) -> str:
    """question, claim or unsure, for one sentence. `alone`: the whole text is this sentence. Among several, the
    writer's own punctuation decides, except that the last may leave out its question mark."""
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
    first, second = words[0], words[1] if len(words) > 1 else ""
    ended = bare.endswith((".", "!"))
    if first in ASKING_WORDS:
        return "question"
    if first in ASKING_FOR_ME:
        return "question" if second in ("me", "us") else "unsure" if alone else "claim"
    if first not in WH_WORDS and first not in AUX_WORDS:
        return "claim"
    if first in ("do", "don't") and (second == "not" or first == "don't" and second not in SUBJECTS):
        return "claim"  # "Do not build ...": an instruction to people
    if not alone:
        return "question" if last and not ended else "claim"
    if ended or first in WH_WORDS and second in SUBJECTS:
        return "unsure"
    return "question"


def kind_of(text: str) -> Kind:
    """statement, question or unsure, by rules (decision D2). The final period or question mark is not always
    there (John, 4 November). Over QUESTION_MAX characters a text is never a question, since Ask would refuse it:
    unsure when it ends with a question mark, so the writer chooses, else a statement."""
    text = " ".join(text.split())
    if not text:
        return "statement"
    if len(text) > QUESTION_MAX:
        return "unsure" if text.rstrip(_CLOSERS).endswith("?") else "statement"
    sentences = _sentences(text)
    kinds = {_sentence_kind(sentence, len(sentences) == 1, number == len(sentences) - 1)
             for number, sentence in enumerate(sentences)}
    if kinds == {"question"}:
        return "question"
    if kinds == {"claim"}:
        return "statement"
    return "unsure"
