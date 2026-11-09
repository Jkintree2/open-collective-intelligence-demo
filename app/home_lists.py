"""v0.3, John's email of 7 November 2026: with Home on, "Recent posts" holds statements and questions from everyone,
mixed newest first, and "My posts" (My statements, renamed while Home is on) holds the member's own the same way.
Everyone's questions come from Q48; a member's own from Q57, which reads who asked
(linked since v0.3, so it holds on every device). A question row takes its time of asking as `created_at` and
`kind` "question", so it sorts and is drawn beside a post (main._decorate_posts gives both their times). A failed
read of the questions is logged and leaves the statements alone, and a question with no words of its own ("Tell me
more", kept before 9 November) is left out of every list, Ask's too."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from app import ask, graph_questions

log = logging.getLogger("oci")
EARLIEST = datetime.min.replace(tzinfo=timezone.utc)


def listed(read: Callable[..., list[dict[str, Any]]], *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """The questions a list shows: those with words of their own, or none if they cannot be read, since a list is
    never worth an error page."""
    try:
        rows = read(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        log.warning(json.dumps({"event": "questions_not_read", "error": type(exc).__name__}))
        return []
    return [row for row in rows if ask.has_own_words(row["text"])]


def _as_posts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**row, "kind": "question", "created_at": row["asked_at"]} for row in rows]


def everyones_questions(limit: int) -> list[dict[str, Any]]:
    return _as_posts(listed(graph_questions.recent, None, limit))


def my_questions(person_key: str, limit: int) -> list[dict[str, Any]]:
    return _as_posts(listed(graph_questions.mine, person_key, limit))


def _time(item: dict[str, Any]) -> datetime:
    at = item.get("created_at")
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)) if at else EARLIEST


def mixed(statements: list[dict[str, Any]], questions: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Newest first, at most `limit`; at the same moment a statement comes before a question."""
    return sorted([*statements, *questions], key=_time, reverse=True)[:limit]
