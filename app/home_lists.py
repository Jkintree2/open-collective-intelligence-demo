"""v0.3, John's email of 7 November 2026: with Home on, "Recent posts" holds statements and questions from everyone,
mixed newest first, and "My posts" (My statements, renamed while Home is on) holds the member's own the same way. A
question links to the answer it last got; a statement shows as the feed draws it. Everyone's questions come from Q48;
a member's own from Q57, which reads who asked (linked since v0.3, so it holds on every device). A failed read of the
questions is logged and leaves the statements alone, as the list under the Ask box does."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app import graph_questions
from app.text import relative_time

log = logging.getLogger("oci")
EARLIEST = datetime.min.replace(tzinfo=timezone.utc)


def utc(value: Any) -> datetime:
    value = value.to_native() if hasattr(value, "to_native") else value
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _read(reader, what: str, *args: Any) -> list[dict[str, Any]]:
    try:
        return reader(*args)
    except Exception as exc:  # noqa: BLE001
        log.warning(json.dumps({"event": "questions_not_read", "list": what, "error": type(exc).__name__}))
        return []


def everyones_questions(limit: int) -> list[dict[str, Any]]:
    return question_items(_read(graph_questions.recent, "recent posts", None, limit))


def my_questions(person_key: str, limit: int) -> list[dict[str, Any]]:
    return question_items(_read(graph_questions.mine, "my posts", person_key, limit))


def question_items(rows: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Each question as _question.html draws it: its time, relative and exact, beside what Q48 or Q57 gave."""
    now = now or datetime.now(timezone.utc)
    items = []
    for row in rows:
        at = utc(row["asked_at"]) if row.get("asked_at") else None
        items.append({**row, "kind": "question", "at": at, "when": relative_time(at, now) if at else "",
                      "iso": at.isoformat() if at else "",
                      "absolute": at.strftime("%Y-%m-%d %H:%M UTC") if at else ""})
    return items


def _time(item: dict[str, Any]) -> datetime:
    at = item.get("at") if item.get("kind") == "question" else item.get("created_at")
    return utc(at) if at else EARLIEST


def mixed(statements: list[dict[str, Any]], questions: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Newest first, at most `limit`; at the same moment a statement comes before a question."""
    return sorted([*statements, *questions], key=_time, reverse=True)[:limit]
