"""Places in the record (03_schema.md, Phase 3, Q43 and Q44): issues near a place, the Near filter's prefill,
and the places of a page of posts. Read only; the place properties are written with the post."""

from typing import Any

from app.graph_runtime import _read

# Q43. Keys of the issues a placed post touches: any edge carrying its id, or a stance on one of its solutions.
ISSUES_NEAR = """
MATCH (post:Post)
WHERE post.place_country = $country
  AND ($area_key IS NULL OR post.place_area_key = $area_key)
WITH collect(post.id) AS ids
MATCH (i:Issue)
WHERE EXISTS { MATCH (i)-[r]-() WHERE r.post_id IN ids }
   OR EXISTS { MATCH (i)-[:HAVE_PROPOSED]->(:Solution)<-[r:APPROVE|OPPOSE]-(:Person)
               WHERE r.post_id IN ids OR r.last_post_id IN ids }
RETURN i.key AS key
"""

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
    return {row["key"] for row in _read(ISSUES_NEAR, country=country, area_key=area_key)}


def last_place(me: str) -> dict[str, Any] | None:
    rows = _read(LAST_PLACE, me=me)
    return rows[0] if rows else None


def post_places(post_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not post_ids:
        return {}
    return {row["id"]: row for row in _read(POST_PLACES, post_ids=post_ids)}
