"""Post and seed write orchestration. Query text stays in graph.py."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from neo4j.exceptions import ServiceUnavailable
from app import graph, graph_evidence
from app.extract import ResolvedPayload
from app.graph_runtime import RecordAsleep
from app.text import make_key

log = logging.getLogger("oci")


def write_payload(tx: Any, payload: ResolvedPayload, common: dict[str, Any], *, one_stance: bool = False,
                  checks: dict[str, dict[str, Any]] | None = None) -> None:
    """Write path statements 3 to 5b for one post (03_schema.md). Posting and editing a post
    (sub-plan D) both write a post's edges through here, so the rules live in one place.
    `one_stance` is the D7 switch: it picks the statement that replaces the person's
    opposite stance; callers that post as an account pass True. `checks` is Phase 2's, from
    check.kept_checks and only with EVIDENCE_CHECK_ENABLED set: None writes evidence exactly as
    Phase 1 does; a dict writes each row's kept reading (or nulls) with statements 5 and 5b extended."""
    for issue in payload.issues:
        tx.run(graph.MERGE_ISSUE_CLAIM, issue_key=issue["key"], issue_name=issue["name"], **common)
    for issue in payload.issues:
        if issue.get("parent_key"):
            tx.run(graph.MERGE_PART_OF, issue_key=issue["key"], parent_key=issue["parent_key"], **common)
    for solution in payload.solutions:
        if not solution.get("stance_only"):
            tx.run(
                graph.MERGE_SOLUTION_PROPOSE,
                solution_key=solution["key"],
                solution_name=solution["name"],
                for_issue_key=solution["for_issue_key"],
                **common,
            )
        stance = graph.STANCE_TYPES.get(solution.get("stance", "none"))
        if stance:
            statement = (graph.MERGE_ONE_STANCE.replace("{other}", graph.OPPOSITE_STANCE[stance])
                         if one_stance else graph.MERGE_STANCE)
            tx.run(statement.replace("{stance}", stance), solution_key=solution["key"], **common)
    for item in payload.evidence:
        rel = graph.EVIDENCE_TYPES[item["stance"]]
        label = item["target_label"]
        if label not in graph.TARGET_LABELS:
            raise ValueError(f"unknown target label {label!r}")
        if checks is None:
            submit, stance, extra, source = graph.MERGE_EVIDENCE_SUBMIT, graph.CREATE_EVIDENCE_STANCE, {}, {}
        else:
            kept = checks.get(item["key"]) or {}
            submit, stance = graph_evidence.MERGE_EVIDENCE_SUBMIT_CHECKED, graph_evidence.CREATE_EVIDENCE_STANCE_CHECKED
            extra = {"check": kept.get("check"), "check_quote": kept.get("check_quote"),
                     "checked_at": kept.get("checked_at"), "check_claim": kept.get("check_claim"),
                     "check_reason": kept.get("check_reason"),
                     # From my own experience: only on a row with no link, never read (03_schema.md).
                     "personal": True if item.get("personal") and not item.get("url") else None}
            source = {"source": kept.get("source")}
        tx.run(
            submit,
            evidence_key=item["key"],
            evidence_name=item["name"],
            url=item.get("url"),
            **source,
            **common,
        )
        tx.run(
            stance.replace("{label}", label).replace("{rel}", rel),
            evidence_key=item["key"],
            target_key=item["target_key"],
            **extra,
            **common,
        )


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
    one_stance: bool = False,
    checks: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Merge one post and everything it adds, in one write transaction. Returns the post id.

    `created_at` and `post_id` are for the seed only; the app never passes them.
    `one_stance` is True for a post by an account, so its stance replaces the person's opposite
    one (D7, from sub-plan C2 on).
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
        write_payload(tx, payload, common, one_stance=one_stance, checks=checks)

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
                **({"checks_kept": sum(1 for row in checks.values() if row.get("check"))} if checks is not None else {}),
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
