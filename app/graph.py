"""The one place Cypher lives (CLAUDE.md rule 6): driver, constraints, the write path, reads."""

from __future__ import annotations

import importlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from neo4j.exceptions import ServiceUnavailable

from app.extract import Candidates, ResolvedPayload
from app.text import make_key
from app.issue_groups import SORTS, group_issues
from app.graph_runtime import (RecordAsleep, _read, _write, close_driver, database, driver, open_driver)

log = logging.getLogger("oci")

STANCE_TYPES = {"approve": "APPROVE", "oppose": "OPPOSE"}
EVIDENCE_TYPES = {"supports": "SUPPORTS", "refutes": "REFUTES"}
TARGET_LABELS = ("Issue", "Solution", "Evidence")


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
  model: $model, latency_ms: $latency_ms, payload: $payload
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
SET child.key = child.key, parent.key = parent.key
WITH child, parent
WHERE child <> parent
  AND NOT (parent)-[:PART_OF]->(:Issue)
  AND NOT (child)-[:PART_OF]->(:Issue)
  AND NOT (:Issue)-[:PART_OF]->(child)
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
ON MATCH  SET hp.last_post_id = $post_id
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
UNWIND [r.post_id, r.last_post_id] AS pid
WITH DISTINCT pid
WHERE pid IS NOT NULL
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
WITH s ORDER BY s.created_at DESC LIMIT 200
OPTIONAL MATCH (i:Issue)-[:HAVE_PROPOSED]->(s)
RETURN s.name AS name, s.key AS key, collect(i.name) AS issues
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

# Q11 uses element ids only inside its transaction so equal keys on different
# labels cannot cause cleanup of an unrelated orphan.
DELETE_POST = """
MATCH (post:Post {id: $id})
OPTIONAL MATCH (a)-[r]->(b)
WHERE r.post_id = $id
  AND type(r) IN ['CLAIM', 'SUBMIT', 'PROPOSE', 'SUPPORTS', 'REFUTES']
WITH post, collect(DISTINCT elementId(a)) + collect(DISTINCT elementId(b)) AS touched,
     collect(r) AS rels
FOREACH (x IN rels | DELETE x)
DETACH DELETE post
RETURN touched
"""
DELETE_POST_ORPHANS = """
MATCH (n)
WHERE elementId(n) IN $touched AND (n:Issue OR n:Solution OR n:Evidence)
  AND coalesce(n.seed, false) = false AND NOT (n)--()
DELETE n
"""
EXPORT_NODES = "MATCH (n) RETURN labels(n) AS labels, properties(n) AS properties"
EXPORT_RELATIONSHIPS = """
MATCH (a)-[r]->(b)
RETURN labels(a) AS source_labels, properties(a) AS source_properties,
       labels(b) AS target_labels, properties(b) AS target_properties,
       type(r) AS type, properties(r) AS properties
"""
# Placeholders below are substituted only after backup validation, from its
# fixed label/type whitelist. Properties and identities always use parameters.
RESTORE_NODE = "MERGE (n:{label} {{{key}: $identity}}) SET n = $properties"
RESTORE_RELATIONSHIP = """
MATCH (a:{source_label} {{{source_key}: $source}}),
      (b:{target_label} {{{target_key}: $target}})
CREATE (a)-[r:{type}]->(b) SET r = $properties
"""

def ensure_constraints() -> None:
    """Run the schema statements from docs/planning/03_schema.md. Idempotent."""
    try:
        for statement in CONSTRAINTS:
            driver().execute_query(statement, database_=database())
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
#
# Post and admin orchestration live in their own modules, and those modules read the query
# text from here. Resolving them on first use rather than importing them at the bottom of
# this file keeps the two directions apart: `import app.graph_posts` on its own works, and
# callers keep writing graph.merge_post().
_ELSEWHERE = {
    "merge_post": "app.graph_posts",
    "create_raw_post": "app.graph_posts",
    "seed_issues": "app.graph_posts",
    "delete_post": "app.graph_backup",
    "export_record": "app.graph_backup",
    "restore_record": "app.graph_backup",
}


def __getattr__(name: str) -> Any:
    if name in _ELSEWHERE:
        return getattr(importlib.import_module(_ELSEWHERE[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    solution_rows = _read(CANDIDATE_SOLUTIONS)
    solutions = {row["key"]: row["name"] for row in solution_rows}
    evidence = {row["key"]: row["name"] for row in _read(CANDIDATE_EVIDENCE)}
    return Candidates(issues=issues, solutions=solutions, evidence=evidence,
                      solution_issues={row["key"]: row["issues"] for row in solution_rows})


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
