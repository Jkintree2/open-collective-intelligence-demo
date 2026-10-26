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
      e.source_published = $source.published, e.source_cites = $source.cites, e.source_checked_at = $now)
WITH e
MATCH (p:Person {key: $person_key})
CREATE (p)-[:SUBMIT {post_id: $post_id, anonymous: $anonymous, created_at: $now}]->(e)
"""

# 5b, extended. {rel} is SUPPORTS or REFUTES and {label} Issue, Solution or Evidence, both from whitelists.
# The revision round adds the writer's sentence, the reading's reason and the personal experience tick
# ($personal is true or null; a null property is not stored). YouTube videos add where the quote is and
# whether the reading rests on a transcript the writer pasted ($check_pasted is true or null). Issue 29 adds
# `answers`: on the writer's own statement, the key of the evidence whose page was read the other way
# (app/sides.py); null, so not stored, on every other edge.
CREATE_EVIDENCE_STANCE_CHECKED = """
MATCH (e:Evidence {key: $evidence_key}), (t:{label} {key: $target_key})
CREATE (e)-[:{rel} {post_id: $post_id, created_at: $now,
                    check: $check, check_quote: $check_quote, checked_at: $checked_at,
                    check_claim: $check_claim, check_reason: $check_reason, personal: $personal,
                    check_quote_at: $check_quote_at, check_pasted: $check_pasted, answers: $answers}]->(t)
"""

# Q35. The readings one post holds on its evidence edges, with what each page says about itself: for the
# edit card (shown on the row) and for the edit's save (a reading the record already holds stays).
POST_CHECKS = """
MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(t)
WHERE r.post_id = $post_id AND r.check IS NOT NULL
RETURN e.key AS evidence_key, t.key AS target_key, e.url AS url, r.check AS check,
       r.check_quote AS check_quote, r.checked_at AS checked_at,
       r.check_claim AS check_claim, r.check_reason AS check_reason,
       r.check_quote_at AS check_quote_at, r.check_pasted AS check_pasted,
       e.source_type AS source_type, e.source_primary AS source_primary, e.source_published AS source_published,
       e.source_cites AS source_cites
"""


def post_checks(post_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    """This post's stored readings, keyed by (evidence key, target key)."""
    return {(row["evidence_key"], row["target_key"]): row for row in _read(POST_CHECKS, post_id=post_id)}


# Q35b (issue 29). The statements one post wrote beside a page read the other way: for the edit card, which
# shows the page's row on the writer's side again and leaves the statement out, since the save rebuilds it.
POST_STATEMENTS = """
MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(t)
WHERE r.post_id = $post_id AND r.answers IS NOT NULL
RETURN e.key AS evidence_key, r.answers AS answers, t.key AS target_key, type(r) AS stance
"""


def post_statements(post_id: str) -> list[dict[str, Any]]:
    """Q35b. Asked only with EVIDENCE_CHECK_ENABLED set."""
    return _read(POST_STATEMENTS, post_id=post_id)


# Q39. Source confidence on one issue page: one row per evidence edge into the issue or one of its
# proposed solutions, with the edge's reading and the evidence's source facts. Q4 and Q5 stay as they
# are; app/confidence.py counts agreement (Q34) and the disagreement line from these rows.
ISSUE_CONFIDENCE = """
MATCH (i:Issue {key: $key})
OPTIONAL MATCH (i)-[:HAVE_PROPOSED]->(s:Solution)
WITH i, collect(s) AS solutions
UNWIND [i] + solutions AS t
MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(t)
RETURN CASE WHEN t:Issue THEN 'issue' ELSE 'solution' END AS target_kind, t.key AS target_key,
       e.key AS evidence_key, type(r) AS stance, r.check AS check,
       r.check_quote AS check_quote, r.check_claim AS check_claim, r.check_reason AS check_reason,
       r.personal AS personal, r.check_quote_at AS check_quote_at, r.check_pasted AS check_pasted,
       r.answers AS answers,
       e.source_checked_at IS NOT NULL AS source_known, e.source_type AS source_type,
       e.source_primary AS source_primary, e.source_published AS source_published,
       e.source_cites AS source_cites
"""


def issue_confidence(key: str) -> list[dict[str, Any]]:
    """Q39's rows for the issue page. Asked only with EVIDENCE_CHECK_ENABLED set."""
    return _read(ISSUE_CONFIDENCE, key=key)
