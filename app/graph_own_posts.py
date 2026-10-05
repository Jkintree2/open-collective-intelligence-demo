"""Editing and deleting one's own post (03_schema.md, Phase 1: Q7 revised, Q24, Q25).
Q11's text stays in graph.py; this module runs it after the ownership check."""

from datetime import datetime
from typing import Any

from neo4j.exceptions import ClientError, ServiceUnavailable

from app import graph, graph_posts
from app.extract import ResolvedPayload
from app.graph_runtime import RecordAsleep, _read, database, driver

# Q24. Is this my post? Seed posts are nobody's to change. The post is locked, so a delete or edit
# of the same post from another tab waits for this transaction, then finds the post gone.
OWN_POST = """
MATCH (:Person {key: $me})-[:POSTED]->(post:Post {id: $id})
WHERE coalesce(post.seed, false) = false
SET post.id = post.id
RETURN post.id AS id, post.text AS text, post.anonymous AS anonymous,
       post.payload AS payload, post.created_at AS created_at
"""

# For the page's answer: gone (no row), someone else's, or mine.
POST_OWNER = """
MATCH (post:Post {id: $id})
OPTIONAL MATCH (author:Person)-[:POSTED]->(post)
RETURN post.id AS id, post.text AS text, post.anonymous AS anonymous, post.payload AS payload,
       post.created_at AS created_at,
       coalesce(author.key = $me AND coalesce(post.seed, false) = false, false) AS mine
"""

# Q7, revised: what the feed needs, as yes or no; the author's key never leaves the record.
POST_FLAGS = """
MATCH (post:Post) WHERE post.id IN $ids
RETURN post.id AS id, post.edited_at AS edited_at,
       EXISTS { MATCH (:Person {key: $me})-[:POSTED]->(post) } AS mine
"""

# Q25 step 1: Q11 statement 1 without deleting the post itself.
DELETE_POST_EDGES = """
MATCH (post:Post {id: $id})
OPTIONAL MATCH (a)-[r]->(b)
WHERE r.post_id = $id
  AND type(r) IN ['CLAIM', 'SUBMIT', 'PROPOSE', 'SUPPORTS', 'REFUTES']
WITH collect(DISTINCT elementId(a)) + collect(DISTINCT elementId(b)) AS touched, collect(r) AS rels
FOREACH (x IN rels | DELETE x)
RETURN touched
"""

# Q25 step 4. created_at stays, so the post keeps its place in the feed.
UPDATE_POST = """
MATCH (post:Post {id: $id})
SET post.text = $text, post.payload = $payload, post.source = $source,
    post.extraction_raw = $extraction_raw, post.model = $model, post.latency_ms = $latency_ms,
    post.edited_at = $now
"""


def post_flags(me: str | None, ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    return {row["id"]: row for row in _read(POST_FLAGS, me=me, ids=ids)}


def post_owner(me: str | None, post_id: str) -> dict[str, Any] | None:
    rows = _read(POST_OWNER, me=me, id=post_id)
    return rows[0] if rows else None


def _write(me: str, post_id: str, work: Any) -> Any:
    try:
        with driver().session(database=database()) as session:
            return session.execute_write(work)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
    except ClientError:
        # Another tab deleted the post while this transaction waited for Q24's lock; Neo4j then
        # refuses to touch the node (EntityNotFound). The post is gone: say so, never a 500.
        if post_owner(me, post_id) is None:
            return False
        raise


def delete_own_post(me: str, post_id: str) -> bool:
    """Q24 then Q11, in one transaction. False when the post is not `me`'s or is gone."""
    def work(tx: Any) -> bool:
        if tx.run(OWN_POST, me=me, id=post_id).single() is None:
            return False
        row = tx.run(graph.DELETE_POST, id=post_id).single()
        if row is None:  # gone a moment ago
            return False
        tx.run(graph.DELETE_POST_ORPHANS, touched=row["touched"]).consume()
        return True
    return _write(me, post_id, work)


def edit_own_post(me: str, post_id: str, payload: ResolvedPayload, *, text: str, source: str,
                  extraction_raw: str | None, model: str | None, latency_ms: int | None, now: datetime) -> bool:
    """Q25, in one transaction: the check, the post's own edges out, the edited card in under the
    same post id, orphans out (after, so a record the new version still uses stays), the post updated.
    An edit is always an account's, so its stances take the one-stance rule (D7)."""
    def work(tx: Any) -> bool:
        row = tx.run(OWN_POST, me=me, id=post_id).single()
        if row is None:
            return False
        touched = tx.run(DELETE_POST_EDGES, id=post_id).single()["touched"]
        common = {"person_key": me, "post_id": post_id, "anonymous": bool(row["anonymous"]),
                  "now": now, "seed": False}
        graph_posts.write_payload(tx, payload, common, one_stance=True)
        tx.run(graph.DELETE_POST_ORPHANS, touched=touched).consume()
        tx.run(UPDATE_POST, id=post_id, text=text, payload=payload.as_json(), source=source,
               extraction_raw=extraction_raw, model=model, latency_ms=latency_ms, now=now).consume()
        return True
    return _write(me, post_id, work)
