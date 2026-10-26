"""Places in the record (03_schema.md, Phase 3, Q43 and Q44): issues near a place, the Near filter's prefill,
and the places of a page of posts. Read only; the place properties are written with the post."""

from typing import Any

from app.graph_runtime import _read

# Q43. Keys of the issues a placed post touches: any edge carrying its id, or a stance on one of its solutions.
# It starts from the placed posts (range indexes) and reads each writer's own edges once, so the cost follows
# the posts placed there, not the size of the record. Every edge a post writes hangs off its writer: CLAIM to
# the issue, PART_OF from it, PROPOSE to a solution its HAVE_PROPOSED joins, SUBMIT to evidence its SUPPORTS or
# REFUTES points at an issue, and a stance (a later post's stance carries last_post_id).
ISSUES_NEAR = """
MATCH (person:Person)-[:POSTED]->(post:Post)
WHERE post.place_country = $country
  AND ($area_key IS NULL OR post.place_area_key = $area_key)
WITH person, post ORDER BY post.created_at DESC LIMIT $post_limit
WITH person, collect(post.id) AS ids
MATCH (person)-[a:CLAIM|PROPOSE|SUBMIT|APPROVE|OPPOSE]->(n)
WHERE a.post_id IN ids OR (type(a) IN ['APPROVE', 'OPPOSE'] AND a.last_post_id IN ids)
WITH a, n, type(a) IN ['APPROVE', 'OPPOSE'] AS stance,
     CASE WHEN a.post_id IN ids THEN a.post_id ELSE a.last_post_id END AS id
UNWIND CASE WHEN n:Issue THEN [n] ELSE [] END
     + [(n)-[r:PART_OF]-(i:Issue) WHERE r.post_id = id | i]
     + [(n)-[r:SUPPORTS|REFUTES]->(i:Issue) WHERE r.post_id = id | i]
     + [(i:Issue)-[r:HAVE_PROPOSED]->(n) WHERE stance OR r.post_id = id | i] AS i
RETURN DISTINCT i.key AS key
LIMIT $issue_limit
"""
# The newest placed posts Q43 reads, and the issues it returns; far above a test group's record.
NEAR_POSTS = 1000
NEAR_ISSUES = 500

# Q43, the prefill: the member's last placed post, anonymous or not (shown only to them).
LAST_PLACE = """
MATCH (:Person {key: $me})-[:POSTED]->(post:Post)
WHERE post.place_country IS NOT NULL
RETURN post.place_country AS country, post.place_area AS area
ORDER BY post.created_at DESC
LIMIT 1
"""

# Q44. The places of a page of posts, by id.
POST_PLACES = """
MATCH (post:Post)
WHERE post.id IN $post_ids AND post.place_country IS NOT NULL
RETURN post.id AS id, post.place_country AS country, post.place_area AS area
"""


def issues_near(country: str, area_key: str | None) -> set[str]:
    return {row["key"] for row in _read(ISSUES_NEAR, country=country, area_key=area_key,
                                          post_limit=NEAR_POSTS, issue_limit=NEAR_ISSUES)}


def last_place(me: str) -> dict[str, Any] | None:
    rows = _read(LAST_PLACE, me=me)
    return rows[0] if rows else None


def post_places(post_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not post_ids:
        return {}
    return {row["id"]: row for row in _read(POST_PLACES, post_ids=post_ids)}
