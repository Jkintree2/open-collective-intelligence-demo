"""Load seed/seed.json through the same write path the app uses (08_architecture.md, decision 10).

    python -m scripts.seed                  reload: idempotent, adds what is missing
    python -m scripts.seed --counts         print node and relationship counts and exit
    python -m scripts.seed --reset --yes    clear everything except the accounts and who entered
                                            whom, then load; refuses when the database holds
                                            anything else that is not seed, unless --force
                                            is also given

The connection comes from the environment (and `.env` when it exists). Production is seeded
from a shell with the variables typed inline, never from a saved file.

Exit codes: 0 loaded, 2 --reset without --yes, 3 refused because non seed nodes exist,
4 a seed statement could not be loaded.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import graph, graph_tidy, tidy
from app.config import load_settings
from app.extract import CardPayload, resolve_payload
from app.text import clean_name, make_key

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "seed.json"


class SeedError(ValueError):
    """A seed statement cannot be loaded as written.

    An ordinary exception, not SystemExit: the admin page calls load() inside a request,
    where a BaseException would slip past the error handler and answer with a blank 500.
    """


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def print_counts() -> None:
    labels, types = graph.counts()
    print("nodes")
    for label, n in labels.items():
        print(f"  {label:10} {n}")
    print("relationships")
    for rel, n in types.items():
        print(f"  {rel:14} {n}")


def _retidied_issue(item: dict, names: dict[str, str]) -> dict:
    return {**item, "name": tidy.retidy(item["name"], names), "parent": tidy.retidy(item.get("parent"), names)}


def _retidied(post: dict, names: dict[str, str]) -> dict:
    """A seed post's card with every issue name read as the issue is now."""
    return {
        "issues": [_retidied_issue(item, names) for item in post["issues"]],
        "solutions": [{**item, "for_issue": tidy.retidy(item.get("for_issue"), names)} for item in post["solutions"]],
        "evidence": [{**item, "about": tidy.retidy(item.get("about"), names)} for item in post["evidence"]],
    }


def load(data: dict) -> tuple[int, int]:
    """Issues block first, then every post not already present. Returns (loaded, skipped)."""
    posts = data["posts"]
    present = graph.existing_post_ids([p["id"] for p in posts])
    if len(present) == len(posts):
        # Everything is there: write nothing, so a seed issue John renamed or merged stays tidied.
        return 0, len(posts)
    # Some are missing (deleted in the back room): load them, reading every seed issue as it is now.
    names = tidy.tidied_names(graph_tidy.renames_and_merges())
    issues = [_retidied_issue(item, names) for item in data["issues"]]
    earliest = min(_parse_time(p["created_at"]) for p in posts)
    graph.seed_issues(issues, created_at=earliest)
    loaded = skipped = 0
    for post in sorted(posts, key=lambda p: p["created_at"]):
        if post["id"] in present:
            skipped += 1
            continue
        author = clean_name(post["author"])
        key = make_key(author)
        if key is None:
            raise SeedError(f"seed post {post['id']} has no usable author name")
        payload = CardPayload.model_validate(_retidied(post, names))
        resolved = resolve_payload(payload, graph.candidates())
        if resolved.dropped:
            raise SeedError(f"seed post {post['id']} lost items: {resolved.dropped}")
        graph.merge_post(
            f"name:{key}",
            author,
            False,
            author,
            post["text"],
            resolved,
            source="seed",
            seed=True,
            post_id=post["id"],
            created_at=_parse_time(post["created_at"]),
        )
        loaded += 1
    return loaded, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--counts", action="store_true", help="print counts and exit")
    parser.add_argument("--reset", action="store_true", help="clear everything except accounts before loading")
    parser.add_argument("--yes", action="store_true", help="confirm --reset")
    parser.add_argument("--force", action="store_true", help="reset even when non-seed nodes exist")
    parser.add_argument("--file", default=str(SEED_FILE))
    args = parser.parse_args(argv)

    settings = load_settings()
    graph.open_driver(settings)
    try:
        graph.ensure_constraints()
        if args.counts:
            print_counts()
            return 0
        if args.reset:
            if not args.yes:
                print("--reset needs --yes", file=sys.stderr)
                return 2
            others = graph.non_seed_count()
            if others and not args.force:
                print(
                    f"refusing: the database holds {others} node(s) that are not seed; "
                    "add --force to delete them",
                    file=sys.stderr,
                )
                return 3
            graph.delete_everything()
            print("cleared everything except the accounts and who entered whom")
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
        try:
            loaded, skipped = load(data)
        except SeedError as exc:
            print(exc, file=sys.stderr)
            return 4
        print(f"loaded {loaded} seed post(s), {skipped} already present")
        print_counts()
        return 0
    finally:
        graph.close_driver()


if __name__ == "__main__":
    sys.exit(main())
