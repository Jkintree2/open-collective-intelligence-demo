"""Post and seed write orchestration. Query text stays in graph.py."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from neo4j.exceptions import ServiceUnavailable
from app import graph
from app.extract import ResolvedPayload
from app.graph_runtime import RecordAsleep
from app.text import make_key

log = logging.getLogger("oci")

def merge_post(
    person_key: str,
    name: str | None,
    anonymous: bool,
    display_name: str | None,
    text: str,
    payload: ResolvedPayload,
    *,
    source: str = "manual",
    seed: bool = False,
    post_id: str | None = None,
    created_at: datetime | None = None,
    extraction_raw: str | None = None,
    model: str | None = None,
    latency_ms: int | None = None,
    request_id: str | None = None,
    edited: bool = False,
) -> str:
    """Merge one post and everything it adds, in one write transaction. Returns the post id.

    `created_at` and `post_id` are for the seed only; the app never passes them.
    """
    post_id = post_id or str(uuid.uuid4())
    now = created_at or datetime.now(timezone.utc)
    if anonymous:
        name = display_name = None
    common = {
        "person_key": person_key,
        "post_id": post_id,
        "anonymous": anonymous,
        "now": now,
        "seed": seed,
    }

    def work(tx: Any) -> None:
        tx.run(graph.MERGE_PERSON, name=name, **common)
        tx.run(
            graph.CREATE_POST,
            text=text,
            display_name=display_name,
            source=source,
            extraction_raw=extraction_raw,
            model=model,
            latency_ms=latency_ms,
            payload=payload.as_json(),
            **common,
        )
        for issue in payload.issues:
            tx.run(graph.MERGE_ISSUE_CLAIM, issue_key=issue["key"], issue_name=issue["name"], **common)
        for issue in payload.issues:
            if issue.get("parent_key"):
                tx.run(graph.MERGE_PART_OF, issue_key=issue["key"], parent_key=issue["parent_key"], **common)
        for solution in payload.solutions:
            tx.run(
                graph.MERGE_SOLUTION_PROPOSE,
                solution_key=solution["key"],
                solution_name=solution["name"],
                for_issue_key=solution["for_issue_key"],
                **common,
            )
            stance = graph.STANCE_TYPES.get(solution.get("stance", "none"))
            if stance:
                tx.run(graph.MERGE_STANCE.replace("{stance}", stance), solution_key=solution["key"], **common)
        for item in payload.evidence:
            tx.run(
                graph.MERGE_EVIDENCE_SUBMIT,
                evidence_key=item["key"],
                evidence_name=item["name"],
                url=item.get("url"),
                **common,
            )
            rel = graph.EVIDENCE_TYPES[item["stance"]]
            label = item["target_label"]
            if label not in graph.TARGET_LABELS:
                raise ValueError(f"unknown target label {label!r}")
            tx.run(
                graph.CREATE_EVIDENCE_STANCE.replace("{label}", label).replace("{rel}", rel),
                evidence_key=item["key"],
                target_key=item["target_key"],
                **common,
            )

    try:
        with graph.driver().session(database=graph.database()) as session:
            session.execute_write(work)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
    log.info(
        json.dumps(
            {
                "event": "merge",
                "request_id": request_id,
                "latency_ms": latency_ms,
                "edited": edited,
                "post_id": post_id,
                "person_key": person_key,
                "source": source,
                "issues": len(payload.issues),
                "solutions": len(payload.solutions),
                "evidence": len(payload.evidence),
            }
        )
    )
    return post_id


def create_raw_post(
    person_key: str, name: str | None, anonymous: bool, display_name: str | None, text: str
) -> str:
    """Store one post with no structure (the plain statement path)."""
    return graph.merge_post(person_key, name, anonymous, display_name, text, ResolvedPayload())


def seed_issues(issues: list[dict[str, Any]], created_at: datetime) -> None:
    """The seed file's issues block: nodes first, then PART_OF, all seed, dated `created_at`."""
    keyed = []
    for item in issues:
        key = make_key(item["name"])
        if key is None:
            raise ValueError(f"seed issue {item['name']!r} has no usable key")
        parent_key = make_key(item["parent"]) if item.get("parent") else None
        keyed.append((key, item["name"], parent_key))

    def work(tx: Any) -> None:
        for key, name, _ in keyed:
            tx.run(graph.MERGE_SEED_ISSUE, key=key, name=name, now=created_at)
        for key, _, parent_key in keyed:
            if parent_key:
                tx.run(graph.MERGE_PART_OF, issue_key=key, parent_key=parent_key, post_id=None, now=created_at)

    try:
        with graph.driver().session(database=graph.database()) as session:
            session.execute_write(work)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
