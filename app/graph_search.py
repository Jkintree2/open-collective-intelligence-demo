"""Keyword search Cypher (03_schema.md, Phase 1, Q26 and Q27)."""

import json
import logging
from typing import Any

from neo4j.exceptions import ClientError

from app.graph_runtime import _read

log = logging.getLogger("oci")

# Q26. Names of issues, solutions and evidence, with the issue each one belongs to.
SEARCH_NAMES = """
CALL db.index.fulltext.queryNodes('record_names', $query) YIELD node, score
WITH node, score ORDER BY score DESC LIMIT 30
OPTIONAL MATCH (node)<-[:HAVE_PROPOSED]-(home:Issue)
OPTIONAL MATCH (node)-[:SUPPORTS|REFUTES]->(target)
OPTIONAL MATCH (target)<-[:HAVE_PROPOSED]-(target_home:Issue)
WITH node, score, collect(DISTINCT home.key) AS solution_homes,
     collect(DISTINCT CASE WHEN target:Issue THEN target.key ELSE target_home.key END) AS evidence_homes
RETURN labels(node)[0] AS label, node.key AS key, node.name AS name, score,
       solution_homes, evidence_homes
ORDER BY score DESC
"""

# Q27. Posts by their text, shaped like the feed.
SEARCH_POSTS = """
CALL db.index.fulltext.queryNodes('post_text', $query) YIELD node, score
WITH node, score ORDER BY score DESC LIMIT 20
RETURN node.id AS id, node.text AS text, node.display_name AS display_name,
       node.anonymous AS anonymous, node.created_at AS created_at, node.seed AS seed,
       node.edited_at AS edited_at
"""


def _search(statement: str, query: str) -> list[dict[str, Any]]:
    try:
        return _read(statement, query=query)
    except ClientError as exc:
        # Escaping should make this unreachable; if Lucene still refuses, the page finds nothing.
        log.warning(json.dumps({"event": "search_refused", "code": exc.code}))
        return []


def search_names(query: str) -> list[dict[str, Any]]:
    return _search(SEARCH_NAMES, query)


def search_posts(query: str) -> list[dict[str, Any]]:
    return _search(SEARCH_POSTS, query)
