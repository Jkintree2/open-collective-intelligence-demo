"""The one place Cypher lives (CLAUDE.md rule 6): driver, constraints, the write path, reads."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from neo4j import Driver, GraphDatabase, RoutingControl
from neo4j.exceptions import ServiceUnavailable

from app.config import Settings
from app.extract import Candidates, ResolvedPayload
from app.text import make_key

log = logging.getLogger("oci")

# How long a managed transaction keeps retrying before the caller hears that the
# database is unreachable. Kept short so the asleep page appears in seconds.
RETRY_SECONDS = 10.0

SORTS = ("people", "recent", "evidence")
STANCE_TYPES = {"approve": "APPROVE", "oppose": "OPPOSE"}
EVIDENCE_TYPES = {"supports": "SUPPORTS", "refutes": "REFUTES"}
TARGET_LABELS = ("Issue", "Solution", "Evidence")


class RecordAsleep(Exception):
    """The database cannot be reached. The tester sees the client facing asleep page."""


CONSTRAINTS = (
    "CREATE CONSTRAINT person_key   IF NOT EXISTS FOR (p:Person)   REQUIRE p.key IS UNIQUE",
    "CREATE CONSTRAINT issue_key    IF NOT EXISTS FOR (i:Issue)    REQUIRE i.key IS UNIQUE",
    "CREATE CONSTRAINT solution_key IF NOT EXISTS FOR (s:Solution) REQUIRE s.key IS UNIQUE",
    "CREATE CONSTRAINT evidence_key IF NOT EXISTS FOR (e:Evidence) REQUIRE e.key IS UNIQUE",
    "CREATE CONSTRAINT post_id      IF NOT EXISTS FOR (p:Post)     REQUIRE p.id IS UNIQUE",
    "CREATE INDEX post_created      IF NOT EXISTS FOR (p:Post)     ON (p.created_at)",
)

# The write path, statement by statement, from docs/planning/03_schema.md.

MERGE_PERSON = """
MERGE (p:Person {key: $person_key})
ON CREATE SET p.name = $name, p.anonymous = $anonymous, p.created_at = $now, p.seed = $seed
ON MATCH  SET p.name = coalesce($name, p.name)
"""

CREATE_POST = """
MATCH (p:Person {key: $person_key})
CREATE (post:Post {
  id: $post_id, text: $text, created_at: $now,
  anonymous: $anonymous, display_name: $display_name, seed: $seed,
  source: $source, extraction_raw: $extraction_raw,
  model: $model, latency_ms: $latency_ms
})
CREATE (p)-[:POSTED {created_at: $now}]->(post)
"""

MERGE_ISSUE_CLAIM = """
MERGE (i:Issue {key: $issue_key})
ON CREATE SET i.name = $issue_name, i.created_at = $now, i.seed = $seed
WITH i
MATCH (p:Person {key: $person_key})
CREATE (p)-[:CLAIM {post_id: $post_id, anonymous: $anonymous, created_at: $now}]->(i)
"""

MERGE_PART_OF = """
MATCH (child:Issue {key: $issue_key}), (parent:Issue {key: $parent_key})
WHERE child <> parent
  AND NOT (parent)-[:PART_OF]->(:Issue)
  AND NOT (child)-[:PART_OF]->(:Issue)
MERGE (child)-[r:PART_OF]->(parent)
ON CREATE SET r.post_id = $post_id, r.created_at = $now
"""

MERGE_SOLUTION_PROPOSE = """
MERGE (s:Solution {key: $solution_key})
ON CREATE SET s.name = $solution_name, s.created_at = $now, s.seed = $seed
WITH s
MATCH (p:Person {key: $person_key}), (i:Issue {key: $for_issue_key})
CREATE (p)-[:PROPOSE {post_id: $post_id, anonymous: $anonymous, created_at: $now}]->(s)
MERGE (i)-[hp:HAVE_PROPOSED]->(s)
ON CREATE SET hp.post_id = $post_id, hp.created_at = $now
"""

# {stance} is APPROVE or OPPOSE, substituted from STANCE_TYPES; never from input.
MERGE_STANCE = """
MATCH (p:Person {key: $person_key}), (s:Solution {key: $solution_key})
MERGE (p)-[r:{stance}]->(s)
ON CREATE SET r.post_id = $post_id, r.anonymous = $anonymous, r.created_at = $now
ON MATCH  SET r.last_post_id = $post_id
"""

MERGE_EVIDENCE_SUBMIT = """
MERGE (e:Evidence {key: $evidence_key})
ON CREATE SET e.name = $evidence_name, e.url = $url, e.created_at = $now, e.seed = $seed
ON MATCH  SET e.url = coalesce(e.url, $url)
WITH e
MATCH (p:Person {key: $person_key})
CREATE (p)-[:SUBMIT {post_id: $post_id, anonymous: $anonymous, created_at: $now}]->(e)
"""

# {rel} is SUPPORTS or REFUTES and {label} Issue, Solution or Evidence, both from whitelists.
CREATE_EVIDENCE_STANCE = """
MATCH (e:Evidence {key: $evidence_key}), (t:{label} {key: $target_key})
CREATE (e)-[:{rel} {post_id: $post_id, created_at: $now}]->(t)
"""

# Seed only: the issues block, merged before any post so PART_OF exists from the start.
MERGE_SEED_ISSUE = """
MERGE (i:Issue {key: $key})
ON CREATE SET i.name = $name, i.created_at = $now, i.seed = true
"""

# Read queries Q1 to Q9 from docs/planning/03_schema.md.

LIST_ISSUES = """
MATCH (i:Issue)
OPTIONAL MATCH (i)-[:PART_OF]->(parent:Issue)
OPTIONAL MATCH (p:Person)-[c:CLAIM]->(i)
WITH i, parent, count(c) AS claims, count(DISTINCT p) AS people,
     collect(DISTINCT p.key) AS person_keys
OPTIONAL MATCH (i)-[:HAVE_PROPOSED]->(s:Solution)
WITH i, parent, claims, people, person_keys, count(DISTINCT s) AS solutions
OPTIONAL MATCH (ev:Evidence)-[:SUPPORTS|REFUTES]->(t)<-[:HAVE_PROPOSED*0..1]-(i)
WITH i, parent, claims, people, person_keys, solutions,
     collect(DISTINCT ev.key) AS evidence_keys
OPTIONAL MATCH (i)-[r]-()
WITH i, parent, claims, people, person_keys, solutions, evidence_keys,
     coalesce(max(r.created_at), i.created_at) AS last_activity
RETURN i.key AS key, i.name AS name, i.seed AS seed,
       parent.key AS parent_key, parent.name AS parent_name,
       claims, people, person_keys, solutions,
       size(evidence_keys) AS evidence, evidence_keys, last_activity
"""

ISSUE_HEADER = """
MATCH (i:Issue {key: $key})
OPTIONAL MATCH (i)-[:PART_OF]->(parent:Issue)
OPTIONAL MATCH (child:Issue)-[:PART_OF]->(i)
RETURN i.key AS key, i.name AS name, i.created_at AS created_at, i.seed AS seed,
       parent.key AS parent_key, parent.name AS parent_name,
       [c IN collect(DISTINCT child) | {key: c.key, name: c.name}] AS children
"""

ISSUE_CLAIMANTS = """
MATCH (p:Person)-[c:CLAIM]->(i:Issue {key: $key})
RETURN count(c) AS claims, count(DISTINCT p) AS people,
       collect(DISTINCT CASE WHEN c.anonymous THEN 'Anonymous' ELSE p.name END) AS names
"""

ISSUE_SOLUTIONS = """
MATCH (i:Issue {key: $key})-[:HAVE_PROPOSED]->(s:Solution)
OPTIONAL MATCH (pp:Person)-[:PROPOSE]->(s)
OPTIONAL MATCH (pa:Person)-[:APPROVE]->(s)
OPTIONAL MATCH (po:Person)-[:OPPOSE]->(s)
WITH s, count(DISTINCT pp) AS proposers, count(DISTINCT pa) AS approves, count(DISTINCT po) AS opposes
OPTIONAL MATCH (ev:Evidence)-[r:SUPPORTS|REFUTES]->(s)
WITH s, proposers, approves, opposes,
     [x IN collect(DISTINCT {key: ev.key, name: ev.name, url: ev.url, stance: type(r)})
        WHERE x.key IS NOT NULL] AS evidence
RETURN s.key AS key, s.name AS name, proposers, approves, opposes, evidence
ORDER BY proposers DESC, approves DESC, s.created_at ASC
"""

ISSUE_EVIDENCE = """
MATCH (ev:Evidence)-[r:SUPPORTS|REFUTES]->(i:Issue {key: $key})
OPTIONAL MATCH (p:Person)-[sub:SUBMIT]->(ev)
RETURN ev.key AS key, ev.name AS name, ev.url AS url, type(r) AS stance,
       collect(DISTINCT CASE WHEN sub.anonymous THEN 'Anonymous' ELSE p.name END) AS submitted_by,
       ev.created_at AS created_at
ORDER BY stance, created_at
"""

ISSUE_POSTS = """
MATCH (i:Issue {key: $key})
OPTIONAL MATCH (child:Issue)-[:PART_OF]->(i)
WITH i, collect(child) AS children
UNWIND [i] + children AS x
MATCH (x)-[r]-()
WHERE r.post_id IS NOT NULL
WITH DISTINCT r.post_id AS pid
MATCH (post:Post {id: pid})
RETURN post.id AS id, post.text AS text, post.display_name AS display_name,
       post.anonymous AS anonymous, post.created_at AS created_at, post.seed AS seed
ORDER BY post.created_at DESC
LIMIT $limit
"""

LIST_POSTS = """
MATCH (post:Post)
RETURN post.id AS id, post.text AS text, post.display_name AS display_name,
       post.anonymous AS anonymous, post.created_at AS created_at, post.seed AS seed
ORDER BY post.created_at DESC
LIMIT $limit
"""

POST_STRUCTURE = """
MATCH (a)-[r]->(b)
WHERE r.post_id IN $post_ids
OPTIONAL MATCH (home:Issue)-[:HAVE_PROPOSED]->(b)
WHERE b:Solution
WITH r, a, b, head(collect(DISTINCT home.key)) AS home_key
RETURN r.post_id AS post_id, labels(a)[0] AS from_label, a.key AS from_key, a.name AS from_name,
       type(r) AS rel, labels(b)[0] AS to_label, b.key AS to_key, b.name AS to_name,
       r.anonymous AS anonymous, home_key
ORDER BY r.created_at
"""

TOP_ISSUES = """
MATCH (i:Issue)
OPTIONAL MATCH (p:Person)-[c:CLAIM]->(i)
WITH i, count(DISTINCT p) AS people, count(c) AS claims
ORDER BY people DESC, claims DESC, i.created_at DESC
LIMIT $limit
RETURN i.key AS key, i.name AS name
"""

CANDIDATE_ISSUES = """
CALL () {
  MATCH (i:Issue)
  OPTIONAL MATCH (i)<-[c:CLAIM]-()
  WITH i, count(c) AS claims
  ORDER BY claims DESC, i.created_at DESC LIMIT 50
  RETURN i
  UNION
  MATCH (i:Issue)
  WITH i ORDER BY i.created_at DESC LIMIT 20
  RETURN i
}
OPTIONAL MATCH (i)-[:PART_OF]->(parent:Issue)
RETURN i.name AS name, i.key AS key, parent.key AS parent_key, parent.name AS parent_name
ORDER BY parent IS NOT NULL, i.name
"""

CANDIDATE_SOLUTIONS = """
MATCH (s:Solution)
RETURN s.name AS name, s.key AS key
ORDER BY s.created_at DESC LIMIT 200
"""

CANDIDATE_EVIDENCE = """
MATCH (e:Evidence)
RETURN e.name AS name, e.key AS key
ORDER BY e.created_at DESC LIMIT 200
"""

COUNT_NODES = "MATCH (n) RETURN count(n) AS n"
COUNT_BY_LABEL = "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label"
COUNT_BY_TYPE = "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY type"
COUNT_NON_SEED = "MATCH (n) WHERE coalesce(n.seed, false) = false RETURN count(n) AS n"
EXISTING_POST_IDS = "MATCH (p:Post) WHERE p.id IN $ids RETURN collect(p.id) AS ids"
DELETE_EVERYTHING = "MATCH (n) DETACH DELETE n"

_driver: Driver | None = None
_database: str = "neo4j"


def open_driver(settings: Settings) -> Driver:
    """Create the process's one driver. A database that does not answer is a warning, not a stop."""
    global _driver, _database
    _driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
        max_transaction_retry_time=RETRY_SECONDS,
    )
    _database = settings.neo4j_database
    try:
        _driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001  a paused database must not stop the process
        log.warning(json.dumps({"event": "database_unreachable", "error": str(exc)}))
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def driver() -> Driver:
    if _driver is None:
        raise RuntimeError("the database driver is not open")
    return _driver


def _read(query: str, **params: Any) -> list[dict[str, Any]]:
    try:
        result = driver().execute_query(
            query, params, database_=_database, routing_=RoutingControl.READ
        )
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
    return [_native(record.data()) for record in result.records]


def _write(query: str, **params: Any) -> None:
    try:
        driver().execute_query(query, params, database_=_database)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc


def _native(row: dict[str, Any]) -> dict[str, Any]:
    """Driver temporal values to Python datetimes, one level deep."""
    for name, value in row.items():
        if hasattr(value, "to_native"):
            row[name] = value.to_native()
    return row


def ensure_constraints() -> None:
    """Run the schema statements from docs/planning/03_schema.md. Idempotent."""
    try:
        for statement in CONSTRAINTS:
            driver().execute_query(statement, database_=_database)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc


def person_key(name: str | None, anonymous: bool, anon_id: str | None) -> str:
    """`anon:<id>` for an anonymous poster, `name:<key>` for a named one."""
    if anonymous:
        return f"anon:{anon_id}"
    key = make_key(name or "")
    if key is None:
        raise ValueError("a named person needs a name with a usable key")
    return f"name:{key}"


# The write path.


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
) -> str:
    """Merge one post and everything it adds, in one write transaction. Returns the post id.

    `created_at` and `post_id` are for the seed only; the app never passes them.
    """
    post_id = post_id or str(uuid.uuid4())
    now = created_at or datetime.now(timezone.utc)
    common = {
        "person_key": person_key,
        "post_id": post_id,
        "anonymous": anonymous,
        "now": now,
        "seed": seed,
    }

    def work(tx: Any) -> None:
        tx.run(MERGE_PERSON, name=name, **common)
        tx.run(
            CREATE_POST,
            text=text,
            display_name=display_name,
            source=source,
            extraction_raw=extraction_raw,
            model=model,
            latency_ms=latency_ms,
            **common,
        )
        for issue in payload.issues:
            tx.run(MERGE_ISSUE_CLAIM, issue_key=issue["key"], issue_name=issue["name"], **common)
        for issue in payload.issues:
            if issue.get("parent_key"):
                tx.run(MERGE_PART_OF, issue_key=issue["key"], parent_key=issue["parent_key"], **common)
        for solution in payload.solutions:
            tx.run(
                MERGE_SOLUTION_PROPOSE,
                solution_key=solution["key"],
                solution_name=solution["name"],
                for_issue_key=solution["for_issue_key"],
                **common,
            )
            stance = STANCE_TYPES.get(solution.get("stance", "none"))
            if stance:
                tx.run(MERGE_STANCE.replace("{stance}", stance), solution_key=solution["key"], **common)
        for item in payload.evidence:
            tx.run(
                MERGE_EVIDENCE_SUBMIT,
                evidence_key=item["key"],
                evidence_name=item["name"],
                url=item.get("url"),
                **common,
            )
            rel = EVIDENCE_TYPES[item["stance"]]
            label = item["target_label"]
            if label not in TARGET_LABELS:
                raise ValueError(f"unknown target label {label!r}")
            tx.run(
                CREATE_EVIDENCE_STANCE.replace("{label}", label).replace("{rel}", rel),
                evidence_key=item["key"],
                target_key=item["target_key"],
                **common,
            )

    try:
        with driver().session(database=_database) as session:
            session.execute_write(work)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
    log.info(
        json.dumps(
            {
                "event": "merge",
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
    return merge_post(person_key, name, anonymous, display_name, text, ResolvedPayload())


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
            tx.run(MERGE_SEED_ISSUE, key=key, name=name, now=created_at)
        for key, _, parent_key in keyed:
            if parent_key:
                tx.run(MERGE_PART_OF, issue_key=key, parent_key=parent_key, post_id=None, now=created_at)

    try:
        with driver().session(database=_database) as session:
            session.execute_write(work)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc


# Reads.


def list_posts(limit: int = 60) -> list[dict[str, Any]]:
    """The newest posts first, `created_at` as a native datetime."""
    return _read(LIST_POSTS, limit=limit)


def issue_posts(key: str, limit: int = 60) -> list[dict[str, Any]]:
    """Posts that touched the issue or, on a parent, any of its sub-issues (Q6)."""
    return _read(ISSUE_POSTS, key=key, limit=limit)


def post_structure(post_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Every edge the given posts created, grouped by post id, in creation order."""
    grouped: dict[str, list[dict[str, Any]]] = {pid: [] for pid in post_ids}
    if not post_ids:
        return grouped
    for row in _read(POST_STRUCTURE, post_ids=post_ids):
        grouped.setdefault(row["post_id"], []).append(row)
    return grouped


def list_issues() -> list[dict[str, Any]]:
    return _read(LIST_ISSUES)


def top_issues(limit: int = 5) -> list[dict[str, Any]]:
    return _read(TOP_ISSUES, limit=limit)


def issue_header(key: str) -> dict[str, Any] | None:
    rows = _read(ISSUE_HEADER, key=key)
    return rows[0] if rows else None


def issue_claimants(key: str) -> dict[str, Any]:
    rows = _read(ISSUE_CLAIMANTS, key=key)
    return rows[0] if rows else {"claims": 0, "people": 0, "names": []}


def issue_solutions(key: str) -> list[dict[str, Any]]:
    return _read(ISSUE_SOLUTIONS, key=key)


def issue_evidence(key: str) -> list[dict[str, Any]]:
    return _read(ISSUE_EVIDENCE, key=key)


def candidates() -> Candidates:
    """What the record holds, for resolving a payload and for the card's autocomplete (Q8)."""
    issues = {
        row["key"]: {"name": row["name"], "parent_key": row["parent_key"]}
        for row in _read(CANDIDATE_ISSUES)
    }
    solutions = {row["key"]: row["name"] for row in _read(CANDIDATE_SOLUTIONS)}
    evidence = {row["key"]: row["name"] for row in _read(CANDIDATE_EVIDENCE)}
    return Candidates(issues=issues, solutions=solutions, evidence=evidence)


def health() -> int:
    """A real read: the number of nodes."""
    return int(_read(COUNT_NODES)[0]["n"])


def counts() -> tuple[dict[str, int], dict[str, int]]:
    """Node counts by label and relationship counts by type, for the seed script and admin."""
    labels = {row["label"]: row["n"] for row in _read(COUNT_BY_LABEL)}
    types = {row["type"]: row["n"] for row in _read(COUNT_BY_TYPE)}
    return labels, types


def non_seed_count() -> int:
    return int(_read(COUNT_NON_SEED)[0]["n"])


def existing_post_ids(ids: list[str]) -> set[str]:
    rows = _read(EXISTING_POST_IDS, ids=ids)
    return set(rows[0]["ids"]) if rows else set()


def delete_everything() -> None:
    """Q10. Reset. Always followed by a seed load."""
    _write(DELETE_EVERYTHING)


# Grouping for the Issues page, in Python (03_schema.md, Q1).


def _sort_key(sort: str):
    if sort == "recent":
        return lambda r: (r["last_activity"],)
    if sort == "evidence":
        return lambda r: (r["evidence"], r["claims"], r["last_activity"])
    return lambda r: (r["people"], r["claims"], r["last_activity"])


def group_issues(rows: list[dict[str, Any]], sort: str = "people") -> list[dict[str, Any]]:
    """Top-level rows with their children attached, ranked on inclusive counts."""
    sort = sort if sort in SORTS else "people"
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        item["own_claims"] = row["claims"]
        item["children"] = []
        by_key[row["key"]] = item
    top: list[dict[str, Any]] = []
    for item in by_key.values():
        parent = by_key.get(item["parent_key"]) if item.get("parent_key") else None
        if parent is not None and parent is not item:
            parent["children"].append(item)
        else:
            top.append(item)
    for item in top:
        if item["children"]:
            family = [item] + item["children"]
            people = set()
            evidence = set()
            for member in family:
                people.update(member.get("person_keys") or [])
                evidence.update(member.get("evidence_keys") or [])
            item["people"] = len(people)
            item["evidence"] = len(evidence)
            item["claims"] = sum(member["own_claims"] for member in family)
            item["solutions"] = sum(member["solutions"] for member in family)
            item["last_activity"] = max(member["last_activity"] for member in family)
            item["children"].sort(key=_sort_key(sort), reverse=True)
    top.sort(key=_sort_key(sort), reverse=True)
    return top
