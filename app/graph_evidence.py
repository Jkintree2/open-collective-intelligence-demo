"""Phase 2: the evidence statements with the check (03_schema.md, "Phase 2: evidence that checks itself").

Used only with EVIDENCE_CHECK_ENABLED set; unset, the write path runs graph.py's statements 5 and 5b
exactly as in Phase 1. graph_posts.write_payload picks between them.
"""

from typing import Any

from app.graph_runtime import _read

# 5, extended. $source is null unless the row's check was kept; the source facts are set once, by the
# first kept reading of the evidence's own link, and a later post never overwrites them.
MERGE_EVIDENCE_SUBMIT_CHECKED = """
MERGE (e:Evidence {key: $evidence_key})
ON CREATE SET e.name = $evidence_name, e.url = $url, e.created_at = $now, e.seed = $seed
ON MATCH  SET e.url = coalesce(e.url, $url)
WITH e
FOREACH (_ IN CASE WHEN $source IS NOT NULL AND e.url = $url AND e.source_checked_at IS NULL THEN [1] ELSE [] END |
  SET e.source_type = $source.type, e.source_primary = $source.primary,
      e.source_published = $source.published, e.source_checked_at = $now)
WITH e
MATCH (p:Person {key: $person_key})
CREATE (p)-[:SUBMIT {post_id: $post_id, anonymous: $anonymous, created_at: $now}]->(e)
"""

# 5b, extended. {rel} is SUPPORTS or REFUTES and {label} Issue, Solution or Evidence, both from whitelists.
CREATE_EVIDENCE_STANCE_CHECKED = """
MATCH (e:Evidence {key: $evidence_key}), (t:{label} {key: $target_key})
CREATE (e)-[:{rel} {post_id: $post_id, created_at: $now,
                    check: $check, check_quote: $check_quote, checked_at: $checked_at}]->(t)
"""

# Q35. The readings one post holds on its evidence edges, with what each page says about itself: for the
# edit card (shown on the row) and for the edit's save (a reading the record already holds stays).
POST_CHECKS = """
MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(t)
WHERE r.post_id = $post_id AND r.check IS NOT NULL
RETURN e.key AS evidence_key, t.key AS target_key, e.url AS url, r.check AS check,
       r.check_quote AS check_quote, r.checked_at AS checked_at,
       e.source_type AS source_type, e.source_primary AS source_primary, e.source_published AS source_published
"""


def post_checks(post_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    """This post's stored readings, keyed by (evidence key, target key)."""
    return {(row["evidence_key"], row["target_key"]): row for row in _read(POST_CHECKS, post_id=post_id)}
