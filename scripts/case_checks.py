"""Machine checks for the reading cases in tests/extraction_cases.json: what a card must hold to pass.

A card is CardPayload.model_dump() after prepared_card, as extract() returns it. A NAME is a string, matched
by its key (make_key), or a list of words that must all be in the name. In an evidence check's "about" a list
is a list of names instead, any of which will do. docs/planning/05_extraction.md has the table."""

import json

from app.text import make_key

COUNTS = {"issues", "solutions", "evidence", "stances", "new_issues"}
STANCES = {"approve", "oppose", "none"}
SIDES = {"supports", "refutes"}
KEYS = {"found", "language_ok", "count", "is", "max", "min", "not", "any", "all", "issue", "solution",
        "for_issue", "stance", "evidence", "url", "about"}


def _kind(check) -> str:
    if not isinstance(check, dict) or not check:
        raise ValueError(f"a check must be an object with a key: {check!r}")
    keys = set(check)
    if keys - KEYS:
        raise ValueError(f"unknown check key {sorted(keys - KEYS)} in {check!r}")
    for kind in ("found", "language_ok", "not", "any", "all", "issue"):
        if keys == {kind}:
            return kind
    if "count" in keys and keys <= {"count", "is", "max", "min"} and len(keys) > 1:
        return "count"
    if "solution" in keys and keys <= {"solution", "stance", "for_issue"}:
        return "solution"
    if keys <= {"evidence", "url", "stance", "about"} and keys & {"evidence", "url", "about"}:
        return "evidence"
    raise ValueError(f"not a check: {check!r}")


def _name(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return isinstance(value, list) and bool(value) and all(isinstance(word, str) and word.strip() for word in value)


def _check_one(check) -> None:
    kind = _kind(check)
    bad = None
    if kind in ("found", "language_ok"):
        bad = type(check[kind]) is not bool
    elif kind == "count":
        bad = check["count"] not in COUNTS or any(
            type(check[limit]) is not int or check[limit] < 0 for limit in ("is", "max", "min") if limit in check)
    elif kind == "not":
        _check_one(check["not"])
    elif kind in ("any", "all"):
        bad = not isinstance(check[kind], list) or not check[kind]
        for inner in check[kind] if not bad else []:
            _check_one(inner)
    elif kind == "issue":
        bad = not _name(check["issue"])
    elif kind == "solution":
        stance = check.get("stance", "none")
        bad = (not _name(check["solution"]) or not isinstance(check.get("for_issue", "x"), str)
               or not set(stance if isinstance(stance, list) else [stance]) <= STANCES)
    else:
        about = check.get("about", "x")
        bad = (("evidence" in check and not _name(check["evidence"]))
               or ("url" in check and check["url"] is not None and not isinstance(check["url"], str))
               or ("stance" in check and check["stance"] not in SIDES)
               or not (isinstance(about, str) or (isinstance(about, list) and about
                                                  and all(isinstance(name, str) for name in about))))
    if bad:
        raise ValueError(f"malformed check: {check!r}")


def validate(checks) -> None:
    """Raises ValueError naming the first check that is not one of the table's."""
    if not isinstance(checks, list):
        raise ValueError(f"checks must be a list: {checks!r}")
    for check in checks:
        _check_one(check)


def _matches(name: str | None, want) -> bool:
    if isinstance(want, str):
        return make_key(name or "") == make_key(want)
    return all(word.lower() in (name or "").lower() for word in want)


def _count(card: dict, what: str) -> int:
    if what == "stances":
        return sum(row.get("stance", "none") != "none" for row in card.get("solutions", []))
    if what == "new_issues":
        return sum(not row.get("existing") for row in card.get("issues", []))
    return len(card.get(what, []))


def _solution(row: dict, check: dict) -> bool:
    stance = check.get("stance")
    return (_matches(row.get("name"), check["solution"])
            and (stance is None or row.get("stance") in (stance if isinstance(stance, list) else [stance]))
            and ("for_issue" not in check or _matches(row.get("for_issue"), check["for_issue"])))


def _evidence(row: dict, check: dict) -> bool:
    about = check.get("about")
    return (("evidence" not in check or _matches(row.get("name"), check["evidence"]))
            and ("url" not in check or row.get("url") == check["url"])
            and ("stance" not in check or row.get("stance") == check["stance"])
            and (about is None or any(_matches(row.get("about"), name)
                                      for name in (about if isinstance(about, list) else [about]))))


def _holds(card: dict, check: dict) -> bool:
    kind = _kind(check)
    if kind in ("found", "language_ok"):
        return card.get(kind) is check[kind]
    if kind == "count":
        n = _count(card, check["count"])
        return (n == check.get("is", n)) and n <= check.get("max", n) and n >= check.get("min", n)
    if kind == "not":
        return not _holds(card, check["not"])
    if kind == "any":
        return any(_holds(card, inner) for inner in check["any"])
    if kind == "all":
        return all(_holds(card, inner) for inner in check["all"])
    if kind == "issue":
        return any(_matches(row.get("name"), check["issue"]) for row in card.get("issues", []))
    if kind == "solution":
        return any(_solution(row, check) for row in card.get("solutions", []))
    return any(_evidence(row, check) for row in card.get("evidence", []))


def failures(card: dict, checks: list[dict]) -> list[str]:
    """One line for each check the card fails; an empty list means it passes."""
    validate(checks)
    lines = []
    for check in checks:
        if not _holds(card, check):
            held = f" (the card holds {_count(card, check['count'])})" if "count" in check else ""
            lines.append(f"not met: {json.dumps(check, ensure_ascii=False)}{held}")
    return lines
