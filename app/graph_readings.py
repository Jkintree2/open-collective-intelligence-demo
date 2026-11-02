"""The back room's readings changed by their writers (03_schema.md Q55). Reads only; never the person behind a post."""

from typing import Any

from app.graph_runtime import _read

# Q55. Every post the language model read, newest change first; app/readings.py keeps those its writer changed.
POSTS_WITH_READINGS = """
MATCH (post:Post)
WHERE post.extraction_raw IS NOT NULL AND coalesce(post.seed, false) = false
RETURN post.id AS id, post.text AS text, post.display_name AS display_name, post.created_at AS created_at,
       post.edited_at AS edited_at, post.payload AS payload, post.extraction_raw AS extraction_raw,
       post.reading_payload AS reading_payload
ORDER BY coalesce(post.edited_at, post.created_at) DESC
LIMIT $limit
"""


def posts_with_readings(limit: int = 200) -> list[dict[str, Any]]:
    return _read(POSTS_WITH_READINGS, limit=limit)
