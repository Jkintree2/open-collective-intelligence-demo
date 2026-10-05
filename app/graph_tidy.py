"""Tidying the issue tree (03_schema.md, Phase 1, Q28 to Q32). Each change runs in one write
transaction with its Change record; the issues are locked first, as in Q23."""

import json
import uuid
from datetime import datetime
from typing import Any

from neo4j.exceptions import ConstraintError, ServiceUnavailable

from app.graph import EVIDENCE_TYPES
from app.graph_runtime import RecordAsleep, _read, database, driver
from app.text import clean_name, make_key

ISSUE_PLACE = """
MATCH (i:Issue {key: $key})
OPTIONAL MATCH (i)-[:PART_OF]->(parent:Issue)
RETURN i.key AS key, i.name AS name, parent.key AS parent_key, parent.name AS parent_name,
       EXISTS { MATCH (:Issue)-[:PART_OF]->(i) } AS has_children
"""

TIDY_CHOICES = """
MATCH (i:Issue {key: $key})
WITH i, EXISTS { MATCH (:Issue)-[:PART_OF]->(i) } AS has_children
OPTIONAL MATCH (other:Issue) WHERE other <> i
OPTIONAL MATCH (other)-[:PART_OF]->(up:Issue)
RETURN has_children, collect({key: other.key, name: other.name, top: up IS NULL}) AS others
"""

# Locks first, reads after (as Q23): a repeated submit waits here and then sees the finished change.
# A key that does not exist is simply not matched. Not `SET i.key = i.key`: a rename that commits while
# this waits would be undone by writing the old key back. The transient property is never committed.
LOCK_ISSUES = "MATCH (i:Issue) WHERE i.key IN $keys SET i.tidy_lock = true REMOVE i.tidy_lock"

# Q28. Under a top-level parent: the guards repeat the one-level rule after the locks.
MOVE_UNDER = """
MATCH (child:Issue {key: $key}), (parent:Issue {key: $parent_key})
WHERE child <> parent
  AND NOT (parent)-[:PART_OF]->(:Issue)
  AND NOT (:Issue)-[:PART_OF]->(child)
OPTIONAL MATCH (child)-[old:PART_OF]->(:Issue)
DELETE old
WITH DISTINCT child, parent
CREATE (child)-[:PART_OF {created_at: $now}]->(parent)
RETURN child.key AS key
"""

MOVE_TOP = """
MATCH (child:Issue {key: $key})-[old:PART_OF]->(:Issue)
DELETE old
"""

# Q29. Refused when another issue has the new key; the constraint backs this up.
RENAME = """
MATCH (i:Issue {key: $key})
WHERE NOT EXISTS { MATCH (other:Issue {key: $new_key}) WHERE other <> i }
SET i.name = $new_name, i.key = $new_key
RETURN i.key AS key
"""

# Q31. In the same transaction as the change it records.
RECORD_CHANGE = """
MATCH (p:Person {key: $person_key}), (i:Issue {key: $issue_key})
CREATE (c:Change {id: $id, kind: $kind, created_at: $now, details: $details})
CREATE (p)-[:MADE {created_at: $now}]->(c)
CREATE (c)-[:CHANGED {created_at: $now}]->(i)
RETURN c.id AS id
"""

# Q32. Ties (two changes in the same instant) are broken by id, so the order never wobbles.
LIST_CHANGES = """
MATCH (p:Person)-[:MADE]->(c:Change)
OPTIONAL MATCH (c)-[:CHANGED]->(i:Issue)
RETURN c.id AS id, c.kind AS kind, c.created_at AS created_at, c.details AS details,
       p.name AS by, i.key AS issue_key, i.name AS issue_name
ORDER BY c.created_at DESC, c.id DESC
LIMIT 200
"""


# Q30. Merge issue B ($merged) into issue A ($kept): every relationship of B moves to A with its
# properties, one statement per type, plain Cypher. A keeps its own place in the tree.
# Both issues are locked by LOCK_ISSUES first; this only reads their names afterwards.
MERGE_LOCK = """
MATCH (a:Issue {key: $kept}), (b:Issue {key: $merged}) WHERE a <> b
RETURN a.name AS kept_name, b.name AS merged_name
"""
MERGE_DROP_LINK = "MATCH (:Issue {key: $kept})-[r:PART_OF]-(:Issue {key: $merged}) DELETE r"
MERGE_CLAIMS = """
MATCH (p:Person)-[r:CLAIM]->(:Issue {key: $merged}), (a:Issue {key: $kept})
CREATE (p)-[n:CLAIM]->(a) SET n = properties(r) DELETE r
RETURN count(*) AS moved
"""
# {rel} is SUPPORTS, then REFUTES, from EVIDENCE_TYPES.
MERGE_EVIDENCE = """
MATCH (e:Evidence)-[r:{rel}]->(:Issue {key: $merged}), (a:Issue {key: $kept})
CREATE (e)-[n:{rel}]->(a) SET n = properties(r) DELETE r
RETURN count(*) AS moved
"""
MERGE_SOLUTIONS = """
MATCH (:Issue {key: $merged})-[r:HAVE_PROPOSED]->(s:Solution), (a:Issue {key: $kept})
MERGE (a)-[n:HAVE_PROPOSED]->(s) ON CREATE SET n = properties(r)
DELETE r
RETURN count(*) AS moved
"""
# B's sub-issues go under A when A is top level, otherwise under A's parent (one level).
MERGE_CHILDREN = """
MATCH (c:Issue)-[r:PART_OF]->(:Issue {key: $merged}), (a:Issue {key: $kept})
OPTIONAL MATCH (a)-[:PART_OF]->(ap:Issue)
WITH c, r, coalesce(ap, a) AS parent
MERGE (c)-[n:PART_OF]->(parent) ON CREATE SET n = properties(r)
DELETE r
RETURN count(*) AS moved
"""
MERGE_DROP_PARENT = "MATCH (:Issue {key: $merged})-[r:PART_OF]->(:Issue) DELETE r"
MERGE_HISTORY = """
MATCH (c:Change)-[r:CHANGED]->(:Issue {key: $merged}), (a:Issue {key: $kept})
CREATE (c)-[n:CHANGED]->(a) SET n = properties(r) DELETE r
RETURN count(*) AS moved
"""
# Plain DELETE, not DETACH: if any relationship was missed, the whole merge fails and nothing changes.
MERGE_DELETE = "MATCH (b:Issue {key: $merged}) DELETE b"

ONE_CHANGE = "MATCH (c:Change {id: $id}) RETURN c.kind AS kind, c.details AS details"


def _write(work: Any) -> Any:
    try:
        with driver().session(database=database()) as session:
            return session.execute_write(work)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc


def _record(tx: Any, me: str, kind: str, issue_key: str, details: dict, now: datetime) -> str:
    change_id = str(uuid.uuid4())
    row = tx.run(RECORD_CHANGE, person_key=me, issue_key=issue_key, id=change_id, kind=kind, now=now,
                 details=json.dumps(details, ensure_ascii=False)).single()
    if row is None:  # never leave a change without its record: roll the whole transaction back
        raise RuntimeError("the change record could not be written")
    return change_id


def issue_place(key: str) -> dict[str, Any] | None:
    rows = _read(ISSUE_PLACE, key=key)
    return rows[0] if rows else None


def tidy_choices(key: str) -> dict[str, Any]:
    rows = _read(TIDY_CHOICES, key=key)
    if not rows:
        return {"parents": [], "others": [], "has_children": False}
    others = sorted((o for o in rows[0]["others"] if o["key"]), key=lambda o: o["name"].lower())
    return {"parents": [{"key": o["key"], "name": o["name"]} for o in others if o["top"]],
            "others": [{"key": o["key"], "name": o["name"]} for o in others],
            "has_children": rows[0]["has_children"]}


def move_issue(me: str, key: str, parent_key: str | None, now: datetime) -> str:
    def work(tx: Any) -> str:
        tx.run(LOCK_ISSUES, keys=[key, parent_key] if parent_key else [key]).consume()
        place = tx.run(ISSUE_PLACE, key=key).single()
        if place is None:
            return "gone"
        if parent_key is None:
            if place["parent_key"] is None:
                return "same"
            tx.run(MOVE_TOP, key=key).consume()
            to = {"to_parent_key": None, "to_parent_name": None}
        else:
            if parent_key == key:
                return "self"
            target = tx.run(ISSUE_PLACE, key=parent_key).single()
            if target is None:
                return "gone"
            if target["parent_key"] is not None:
                return "parent_is_sub"
            if place["has_children"]:
                return "has_children"
            if place["parent_key"] == parent_key:
                return "same"
            if tx.run(MOVE_UNDER, key=key, parent_key=parent_key, now=now).single() is None:
                # Changed between the reads above and the locks: read again to say which rule refused.
                again = tx.run(ISSUE_PLACE, key=key).single()
                if again is None:
                    return "gone"
                if again["has_children"]:
                    return "has_children"
                recheck = tx.run(ISSUE_PLACE, key=parent_key).single()
                if recheck is None:
                    return "gone"
                return "parent_is_sub"
            to = {"to_parent_key": parent_key, "to_parent_name": target["name"]}
        _record(tx, me, "move", key, {"issue_key": key, "issue_name": place["name"],
                                      "from_parent_key": place["parent_key"],
                                      "from_parent_name": place["parent_name"], **to}, now)
        return "moved"
    return _write(work)


def rename_issue(me: str, key: str, new_name: str, now: datetime) -> tuple[str, str]:
    name = clean_name(new_name)
    new_key = make_key(name)
    if new_key is None:
        return "short", key

    def work(tx: Any) -> tuple[str, str]:
        tx.run(LOCK_ISSUES, keys=[key, new_key]).consume()
        place = tx.run(ISSUE_PLACE, key=key).single()
        if place is None:
            # A repeated submit: the first one already renamed it to exactly this.
            done = tx.run(ISSUE_PLACE, key=new_key).single()
            return ("same", new_key) if done is not None and done["name"] == name else ("gone", key)
        if name == place["name"]:
            return "same", key
        if tx.run(RENAME, key=key, new_key=new_key, new_name=name).single() is None:
            return "taken", key
        _record(tx, me, "rename", new_key, {"from_key": key, "from_name": place["name"],
                                            "to_key": new_key, "to_name": name}, now)
        return "renamed", new_key
    try:
        return _write(work)
    except ConstraintError:
        return "taken", key


def list_changes() -> list[dict[str, Any]]:
    return _read(LIST_CHANGES)


def change(change_id: str) -> dict[str, Any] | None:
    rows = _read(ONE_CHANGE, id=change_id) if change_id else []
    return rows[0] if rows else None


def merge_issues(me: str, kept: str, merged: str, now: datetime) -> tuple[str, str | None]:
    if kept == merged:
        return "self", None

    def work(tx: Any) -> tuple[str, str | None]:
        keys = {"kept": kept, "merged": merged}
        tx.run(LOCK_ISSUES, keys=[kept, merged]).consume()
        names = tx.run(MERGE_LOCK, **keys).single()
        if names is None:
            return "gone", None
        tx.run(MERGE_DROP_LINK, **keys).consume()
        moved = {"CLAIM": tx.run(MERGE_CLAIMS, **keys).single()["moved"]}
        for rel in EVIDENCE_TYPES.values():
            moved[rel] = tx.run(MERGE_EVIDENCE.replace("{rel}", rel), **keys).single()["moved"]
        moved["HAVE_PROPOSED"] = tx.run(MERGE_SOLUTIONS, **keys).single()["moved"]
        moved["PART_OF"] = tx.run(MERGE_CHILDREN, **keys).single()["moved"]
        tx.run(MERGE_DROP_PARENT, **keys).consume()
        moved["CHANGED"] = tx.run(MERGE_HISTORY, **keys).single()["moved"]
        tx.run(MERGE_DELETE, merged=merged).consume()
        change_id = _record(tx, me, "merge", kept, {"kept_key": kept, "kept_name": names["kept_name"],
                                                    "merged_key": merged, "merged_name": names["merged_name"],
                                                    "moved": moved}, now)
        return "merged", change_id
    return _write(work)
