"""The one place Cypher lives (CLAUDE.md rule 6): driver, constraints, raw posts, feed, health."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from neo4j import Driver, GraphDatabase, RoutingControl
from neo4j.exceptions import ServiceUnavailable

from app.config import Settings
from app.text import make_key

log = logging.getLogger("oci")

# How long a managed transaction keeps retrying before the caller hears that the
# database is unreachable. Kept short so the asleep page appears in seconds.
RETRY_SECONDS = 10.0


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

MERGE_PERSON = """
MERGE (p:Person {key: $person_key})
ON CREATE SET p.name = $name, p.anonymous = $anonymous, p.created_at = datetime()
"""

CREATE_POST = """
MATCH (p:Person {key: $person_key})
CREATE (post:Post {
  id: $post_id, text: $text, created_at: datetime(),
  anonymous: $anonymous, display_name: $display_name, seed: false,
  source: 'manual', extraction_raw: null
})
CREATE (p)-[:POSTED {created_at: datetime()}]->(post)
"""

LIST_POSTS = """
MATCH (post:Post)
RETURN post.id AS id, post.text AS text, post.display_name AS display_name,
       post.anonymous AS anonymous, post.created_at AS created_at, post.seed AS seed
ORDER BY post.created_at DESC
LIMIT $limit
"""

COUNT_NODES = "MATCH (n) RETURN count(n) AS n"

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


def create_raw_post(
    person_key: str, name: str | None, anonymous: bool, display_name: str | None, text: str
) -> str:
    """Store one post with no structure, in one write transaction. Returns the post id."""
    post_id = str(uuid.uuid4())

    def work(tx: Any) -> None:
        tx.run(MERGE_PERSON, person_key=person_key, name=name, anonymous=anonymous)
        tx.run(
            CREATE_POST,
            person_key=person_key,
            post_id=post_id,
            text=text,
            anonymous=anonymous,
            display_name=display_name,
        )

    try:
        with driver().session(database=_database) as session:
            session.execute_write(work)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
    return post_id


def list_posts(limit: int = 60) -> list[dict[str, Any]]:
    """The newest posts first, `created_at` as a native datetime."""
    try:
        result = driver().execute_query(
            LIST_POSTS, {"limit": limit}, database_=_database, routing_=RoutingControl.READ
        )
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
    posts = []
    for record in result.records:
        row = record.data()
        created = row.get("created_at")
        if created is not None and hasattr(created, "to_native"):
            row["created_at"] = created.to_native()
        posts.append(row)
    return posts


def health() -> int:
    """A real read: the number of nodes."""
    try:
        result = driver().execute_query(
            COUNT_NODES, database_=_database, routing_=RoutingControl.READ
        )
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
    return int(result.records[0]["n"])
