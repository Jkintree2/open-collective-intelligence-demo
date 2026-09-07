"""Load seed/seed.json through the same write path the app uses (08_architecture.md, decision 10).

    python -m scripts.seed                  reload: idempotent, adds what is missing
    python -m scripts.seed --counts         print node and relationship counts and exit
    python -m scripts.seed --reset --yes    delete everything, then load; refuses when the
                                            database holds any node without seed = true
                                            unless --force is also given

The connection comes from the environment (and `.env` when it exists). Production is seeded
from a shell with the variables typed inline, never from a saved file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import graph
from app.config import load_settings
from app.extract import CardPayload, resolve_payload
from app.text import clean_name, make_key

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "seed.json"


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


def load(data: dict) -> tuple[int, int]:
    """Issues block first, then every post not already present. Returns (loaded, skipped)."""
    posts = data["posts"]
    earliest = min(_parse_time(p["created_at"]) for p in posts)
    graph.seed_issues(data["issues"], created_at=earliest)
    present = graph.existing_post_ids([p["id"] for p in posts])
    loaded = skipped = 0
    for post in sorted(posts, key=lambda p: p["created_at"]):
        if post["id"] in present:
            skipped += 1
            continue
        author = clean_name(post["author"])
        key = make_key(author)
        if key is None:
            raise SystemExit(f"seed post {post['id']} has no usable author name")
        payload = CardPayload.model_validate(
            {"issues": post["issues"], "solutions": post["solutions"], "evidence": post["evidence"]}
        )
        resolved = resolve_payload(payload, graph.candidates())
        if resolved.dropped:
            raise SystemExit(f"seed post {post['id']} lost items: {resolved.dropped}")
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
    parser.add_argument("--reset", action="store_true", help="delete everything before loading")
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
            print("deleted everything")
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
        loaded, skipped = load(data)
        print(f"loaded {loaded} seed post(s), {skipped} already present")
        print_counts()
        return 0
    finally:
        graph.close_driver()


if __name__ == "__main__":
    sys.exit(main())
