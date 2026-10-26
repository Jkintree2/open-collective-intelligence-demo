"""Phase 3, ask the record: the fixture record and the live case runner.

    python -m scripts.asks --load            wipe the disposable test Neo4j and load seed/seed.json, then
                                             tests/fixtures/ask_record.json, through the app's write path
    python -m scripts.asks --cases [A1,A5]   ask each case in tests/ask_cases.json of that record and
                                             print the answer, its sources, what the guard dropped,
                                             tokens and cache hits (needs LLM_API_KEY)

The database is the disposable one named by OCI_TEST_NEO4J_URI (password OCI_TEST_NEO4J_PASSWORD), on
this machine and never on port 7687, as for the live tests. The reading service is LLM_API_KEY,
LLM_BASE_URL and LLM_MODEL from the environment; the key is never printed.
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

from dataclasses import replace

from app import ask, graph, graph_own_posts, graph_stances
from app.config import DEFAULT_LLM_BASE_URL, DEFAULT_LLM_MODEL, Settings
from app.extract import CardPayload, resolve_payload
from app.text import make_key
from scripts import seed

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "ask_record.json"
CASES = Path(__file__).resolve().parent.parent / "tests" / "ask_cases.json"


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


def run_cases(settings: Settings, only: set[str] | None = None) -> dict[str, int]:
    """Each case asked once, printed for reading by hand; returns the totals."""
    totals = {"cases": 0, "prompt_tokens": 0, "prompt_cache_hit_tokens": 0, "completion_tokens": 0,
              "sources_dropped": 0, "paragraphs_dropped": 0, "failed": 0}
    for case in json.loads(CASES.read_text(encoding="utf-8"))["cases"]:
        if only and case["id"] not in only:
            continue
        digest = ask.issue_digest(case["issue"]) if case["issue"] else ask.record_digest(case["question"])
        result = ask.answer(case["question"], case.get("earlier", []), digest, settings,
                            scope="issue" if case["issue"] else "record", request_id=case["id"])
        line = result.log
        print(f"\n=== {case['id']} ({case['issue'] or 'whole record'}): {case['question']}")
        if case.get("earlier"):
            print(f"    earlier: {case['earlier']}")
        print(f"    expect: {case['expect']}")
        print(f"    read: {', '.join(digest.issue_keys)}; digest {digest.chars} characters, "
              f"{digest.posts_in} posts in, {digest.posts_left_out} left out")
        print(f"    {result.status}" + (f": {result.message}" if result.message else ""))
        for paragraph in result.paragraphs:
            print(f"    | {paragraph['text']} {' '.join(f'[{n}]' for n in paragraph['refs'])}")
        for n, source in enumerate(result.sources, 1):
            print(f"    {n}. {source.id} {source.name}{', ' + source.when if source.when else ''}"
                  f"{': ' + source.text[:80] if source.text else ''}")
        if result.partial:
            print(f"    {ask.PARTIAL}")
        print("    in_record {in_record}; paragraphs kept {paragraphs}, dropped {paragraphs_dropped}; sources kept "
              "{sources_kept}, dropped {sources_dropped}; tokens in {prompt_tokens} (cache hits "
              "{prompt_cache_hit_tokens}), out {completion_tokens}; {latency_ms} ms".format_map(
                  {key: line.get(key) for key in ("in_record", "paragraphs", "paragraphs_dropped", "sources_kept",
                                                  "sources_dropped", "prompt_tokens", "prompt_cache_hit_tokens",
                                                  "completion_tokens", "latency_ms")}))
        totals["cases"] += 1
        totals["failed"] += result.status == "failed"
        for key in ("prompt_tokens", "prompt_cache_hit_tokens", "completion_tokens", "sources_dropped",
                    "paragraphs_dropped"):
            totals[key] += line.get(key) or 0
    print("\ntotals: " + json.dumps(totals))
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--load", action="store_true", help="wipe the test database and load the fixture")
    parser.add_argument("--cases", nargs="?", const="", default=None, help="run the cases (all, or ids like A1,A5)")
    args = parser.parse_args(argv)
    if not args.load and args.cases is None:
        parser.print_help()
        return 2
    settings = test_settings()
    if args.cases is not None:
        if not os.environ.get("LLM_API_KEY"):
            raise SystemExit("set LLM_API_KEY to run the cases")
        settings = replace(settings, llm_api_key=os.environ["LLM_API_KEY"],
                           llm_base_url=os.environ.get("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL,
                           llm_model=os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL)
    graph.open_driver(settings)
    try:
        if args.load:
            graph.ensure_constraints()
            graph.delete_everything()  # the fixture's people have no email, so nothing is kept
            load_fixture()
            seed.print_counts()
        if args.cases is not None:
            totals = run_cases(settings, set(filter(None, args.cases.split(","))) or None)
            return 1 if totals["failed"] else 0
        return 0
    finally:
        graph.close_driver()


if __name__ == "__main__":
    sys.exit(main())
