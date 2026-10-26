"""Phase 3, ask the record: the fixture record and the live case runner.

    python -m scripts.asks --load       wipe the disposable test Neo4j and load seed/seed.json, then
                                        tests/fixtures/ask_record.json, through the app's write path

The database is the disposable one named by OCI_TEST_NEO4J_URI (password OCI_TEST_NEO4J_PASSWORD), on
this machine and never on port 7687, as for the live tests. It never reads `.env`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app import graph, graph_own_posts, graph_stances
from app.config import Settings
from app.extract import CardPayload, resolve_payload
from app.text import make_key
from scripts import seed

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "ask_record.json"


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _resolved(card: dict[str, Any]):
    payload = CardPayload.model_validate({name: card[name] for name in ("issues", "solutions", "evidence")})
    resolved = resolve_payload(payload, graph.candidates())
    if resolved.dropped:
        raise ValueError(f"fixture card lost items: {resolved.dropped}")
    return resolved


def _checks(card: dict[str, Any], at: datetime) -> dict[str, dict[str, Any]]:
    """The readings the fixture gives, keyed by evidence key as graph_posts.write_payload wants them."""
    out = {}
    for name, kept in (card.get("checks") or {}).items():
        out[make_key(name)] = {**kept, "checked_at": at} if kept.get("check") else {}
    return out


def load_fixture(data: dict[str, Any] | None = None) -> None:
    """The seed, then the fixture's posts oldest first (as accounts, so one stance per person), its
    edits and its clicks. Expects an empty database with the app's constraints."""
    data = data or json.loads(FIXTURE.read_text(encoding="utf-8"))
    seed.load(json.loads(seed.SEED_FILE.read_text(encoding="utf-8")))
    for post in sorted(data["posts"], key=lambda p: p["created_at"]):
        at, hidden = _time(post["created_at"]), bool(post["anonymous"])
        name = None if hidden else post["author"]
        graph.merge_post(post["account"], name, hidden, name, post["text"], _resolved(post), source="fixture",
                         post_id=post["id"], created_at=at, one_stance=True, checks=_checks(post, at))
        if (edit := post.get("edit")):
            edited_at = _time(edit["at"])
            if not graph_own_posts.edit_own_post(post["account"], post["id"], _resolved(edit), text=edit["text"],
                                                 source="fixture", extraction_raw=None, model=None,
                                                 latency_ms=None, now=edited_at, checks=_checks(edit, edited_at)):
                raise ValueError(f"fixture edit of {post['id']} was refused")
    for click in data.get("clicks", []):
        if graph_stances.set_stance(click["account"], make_key(click["solution"]), click["stance"],
                                    _time(click["at"])) is None:
            raise ValueError(f"fixture click on {click['solution']!r} found nothing")


def test_settings() -> Settings:
    """The disposable test Neo4j, refused unless it is on this machine and not on port 7687."""
    uri = os.environ.get("OCI_TEST_NEO4J_URI", "")
    parts = urlsplit(uri)
    if parts.hostname not in ("localhost", "127.0.0.1", "::1") or parts.port in (None, 7687):
        raise SystemExit("set OCI_TEST_NEO4J_URI to the disposable test Neo4j on this machine (never port 7687)")
    return Settings("unused", "unused", "unused", uri, "neo4j", os.environ.get("OCI_TEST_NEO4J_PASSWORD", "testpass1"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--load", action="store_true", help="wipe the test database and load the fixture")
    args = parser.parse_args(argv)
    if not args.load:
        parser.print_help()
        return 2
    graph.open_driver(test_settings())
    try:
        graph.ensure_constraints()
        graph.delete_everything()  # the fixture's people have no email, so nothing is kept
        load_fixture()
        seed.print_counts()
        return 0
    finally:
        graph.close_driver()


if __name__ == "__main__":
    sys.exit(main())
