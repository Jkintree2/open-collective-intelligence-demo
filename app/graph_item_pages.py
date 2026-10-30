"""GitHub issue 55 (John, 30 October 2026): the reads behind a solution's page and a piece of evidence's page
(03_schema.md, Q50 to Q54). Read only. Names behind anonymous edges are never read: a proposer or submitter
who posted anonymously comes back as "Anonymous", and people are counted by account and anonymity as Q3
counts them (D2)."""

from typing import Any

from app.graph_runtime import _read

# Q50. A solution's page: its issues in the order they took it up (each with its parent, for the
# breadcrumbs), who proposed it, its stance counts with the member's own ($me null matches nothing), and
# its evidence, one row per piece and side.
SOLUTION_PAGE = """
MATCH (s:Solution {key: $key})
CALL (s) {
  OPTIONAL MATCH (home:Issue)-[:HAVE_PROPOSED]->(s)
  OPTIONAL MATCH (home)-[:PART_OF]->(parent:Issue)
  WITH home, parent ORDER BY home.created_at
  RETURN [h IN collect({key: home.key, name: home.name, parent_key: parent.key, parent_name: parent.name})
          WHERE h.key IS NOT NULL] AS issues
}
CALL (s) {
  OPTIONAL MATCH (p:Person)-[pr:PROPOSE]->(s)
  WITH p.key + CASE WHEN coalesce(pr.anonymous, false) THEN '|anonymous' ELSE '' END AS who,
       CASE WHEN coalesce(pr.anonymous, false) THEN 'Anonymous' ELSE p.name END AS shown
  RETURN count(DISTINCT who) AS proposers, collect(DISTINCT shown) AS proposed_by
}
CALL (s) {
  OPTIONAL MATCH (:Person {key: $me})-[mine:APPROVE|OPPOSE]->(s)
  RETURN head(collect(type(mine))) AS my_stance
}
CALL (s) {
  OPTIONAL MATCH (ev:Evidence)-[r:SUPPORTS|REFUTES]->(s)
  WITH DISTINCT ev, type(r) AS stance
  ORDER BY ev.created_at
  RETURN [x IN collect({key: ev.key, name: ev.name, url: ev.url, stance: stance}) WHERE x.key IS NOT NULL]
         AS evidence
}
RETURN s.key AS key, s.name AS name, issues, proposers, proposed_by,
       COUNT { (:Person)-[:APPROVE]->(s) } AS approves, COUNT { (:Person)-[:OPPOSE]->(s) } AS opposes,
       my_stance, evidence
"""

# Q51 and Q53. The posts that mention a solution or a piece of evidence: every edge that touches it, as Q6
# reads an issue's (a later post that said the same carries last_post_id). Shaped like the feed.
_ITEM_POSTS = """
UNWIND [(x)-[r]-() | r] AS r
UNWIND [r.post_id, r.last_post_id] AS pid
WITH DISTINCT pid
WHERE pid IS NOT NULL
MATCH (post:Post {id: pid})
RETURN post.id AS id, post.text AS text, post.display_name AS display_name,
       post.anonymous AS anonymous, post.created_at AS created_at, post.seed AS seed
ORDER BY post.created_at DESC
LIMIT $limit
"""
SOLUTION_POSTS = "MATCH (x:Solution {key: $key})" + _ITEM_POSTS
EVIDENCE_POSTS = "MATCH (x:Evidence {key: $key})" + _ITEM_POSTS

# Q52. A piece of evidence's page: who submitted it, what it supports or refutes (an issue, a solution with
# the issue that first took it up, or other evidence; with that issue's parent, for the breadcrumbs), the
# evidence on it, whether a writer gave it as personal experience, the page it answers (issue 29), and what
# its page says about itself (Phase 2).
EVIDENCE_PAGE = """
MATCH (e:Evidence {key: $key})
CALL (e) {
  OPTIONAL MATCH (p:Person)-[sub:SUBMIT]->(e)
  RETURN collect(DISTINCT CASE WHEN sub.anonymous THEN 'Anonymous' ELSE p.name END) AS submitted_by
}
CALL (e) {
  OPTIONAL MATCH (e)-[r:SUPPORTS|REFUTES]->(t)
  WITH DISTINCT t, type(r) AS stance
  OPTIONAL MATCH (home:Issue)-[:HAVE_PROPOSED]->(t)
  WITH t, stance, home ORDER BY home.created_at
  WITH t, stance, head(collect(home)) AS home
  WITH t, stance, home, CASE WHEN t:Issue THEN t ELSE home END AS issue
  OPTIONAL MATCH (issue)-[:PART_OF]->(parent:Issue)
  WITH t, stance, home, parent ORDER BY t.created_at
  RETURN [x IN collect({kind: CASE WHEN t:Issue THEN 'issue' WHEN t:Solution THEN 'solution' ELSE 'evidence' END,
                        key: t.key, name: t.name, stance: stance, home_key: home.key, home_name: home.name,
                        parent_key: parent.key, parent_name: parent.name})
          WHERE x.key IS NOT NULL] AS targets
}
CALL (e) {
  OPTIONAL MATCH (other:Evidence)-[r:SUPPORTS|REFUTES]->(e)
  WITH DISTINCT other, type(r) AS stance
  ORDER BY other.created_at
  RETURN [x IN collect({key: other.key, name: other.name, url: other.url, stance: stance}) WHERE x.key IS NOT NULL]
         AS evidence
}
CALL (e) {
  OPTIONAL MATCH (e)-[r:SUPPORTS|REFUTES]->()
  WITH collect(r) AS edges
  OPTIONAL MATCH (page:Evidence {key: head([r IN edges WHERE r.answers IS NOT NULL | r.answers])})
  RETURN any(r IN edges WHERE r.personal) AS personal, page.key AS answers_key, page.name AS answers_name
}
RETURN e.key AS key, e.name AS name, e.url AS url, submitted_by, targets, evidence, personal,
       answers_key, answers_name,
       e.source_checked_at IS NOT NULL AS source_known, e.source_type AS source_type,
       e.source_primary AS source_primary, e.source_published AS source_published, e.source_cites AS source_cites
"""

# Q54. Source confidence on the evidence page, with EVIDENCE_CHECK_ENABLED: Q39's columns for every evidence
# edge into what this piece supports or refutes, so agreement there is counted as the issue page counts it.
EVIDENCE_CONFIDENCE = """
MATCH (:Evidence {key: $key})-[:SUPPORTS|REFUTES]->(t)
WITH DISTINCT t
MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(t)
RETURN CASE WHEN t:Issue THEN 'issue' WHEN t:Solution THEN 'solution' ELSE 'evidence' END AS target_kind,
       t.key AS target_key, e.key AS evidence_key, type(r) AS stance, r.check AS check,
       r.check_quote AS check_quote, r.check_claim AS check_claim, r.check_reason AS check_reason,
       r.personal AS personal, r.check_quote_at AS check_quote_at, r.check_pasted AS check_pasted,
       r.answers AS answers,
       e.source_checked_at IS NOT NULL AS source_known, e.source_type AS source_type,
       e.source_primary AS source_primary, e.source_published AS source_published,
       e.source_cites AS source_cites
"""


def solution(key: str, me: str | None = None) -> dict[str, Any] | None:
    """Q50, or None when the record has no such solution."""
    rows = _read(SOLUTION_PAGE, key=key, me=me)
    return rows[0] if rows else None


def solution_posts(key: str, limit: int = 60) -> list[dict[str, Any]]:
    """Q51."""
    return _read(SOLUTION_POSTS, key=key, limit=limit)


def evidence(key: str) -> dict[str, Any] | None:
    """Q52, or None when the record has no such evidence."""
    rows = _read(EVIDENCE_PAGE, key=key)
    return rows[0] if rows else None


def evidence_posts(key: str, limit: int = 60) -> list[dict[str, Any]]:
    """Q53."""
    return _read(EVIDENCE_POSTS, key=key, limit=limit)


def evidence_confidence(key: str) -> list[dict[str, Any]]:
    """Q54's rows. Asked only with EVIDENCE_CHECK_ENABLED set."""
    return _read(EVIDENCE_CONFIDENCE, key=key)
