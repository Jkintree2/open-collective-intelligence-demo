"""Phase 3, ask the record: the reads behind an answer (03_schema.md, Phase 3, Q40 to Q42; since GitHub issue
55 also for one solution and one piece of evidence). Read only.

app/ask.py turns the rows into the digest the reading service sees. Nothing here returns an email,
a country, a postal code or the name behind an anonymous edge: stances come as counts, dates and the
posts that took them, and a post's name is read from the post itself (Q6).
"""

from typing import Any

from app.graph_runtime import _read

SOLUTION_LIMIT = 20  # solutions on one issue and its sub-issues
STANCE_LIMIT = 20    # dated stances listed under one solution, newest first; the counts are always whole
EVIDENCE_LIMIT = 10  # evidence record-wide
EDGE_LIMIT = 300     # evidence rows on one issue

# One solution's columns, shared by Q40 and Q42: its issues, proposers counted as in Q4 (by account and
# anonymity, D2), the posts that proposed it, and its stances newest first, each with its date, whether
# it was a click, and the posts that took it (the first and, when a later post said the same, that one).
_SOLUTION_COLUMNS = """
CALL (s) {
  OPTIONAL MATCH (home:Issue)-[:HAVE_PROPOSED]->(s)
  WITH home ORDER BY home.created_at
  RETURN [h IN collect({key: home.key, name: home.name}) WHERE h.key IS NOT NULL] AS issues
}
CALL (s) {
  OPTIONAL MATCH (pp:Person)-[pr:PROPOSE]->(s)
  RETURN count(DISTINCT pp.key + CASE WHEN coalesce(pr.anonymous, false) THEN '|anonymous' ELSE '' END) AS proposers,
         [x IN collect(DISTINCT pr.post_id) WHERE x IS NOT NULL] AS proposed_in
}
CALL (s) {
  OPTIONAL MATCH (:Person)-[st:APPROVE|OPPOSE]->(s)
  WITH st ORDER BY st.created_at DESC
  RETURN [x IN collect({stance: toLower(type(st)), date: toString(date(st.created_at)),
                        click: coalesce(st.source = 'click', false),
                        post_ids: [p IN [st.post_id, st.last_post_id] WHERE p IS NOT NULL]})
          WHERE x.stance IS NOT NULL][..$stance_limit] AS stances
}
RETURN s.key AS key, s.name AS name, issues, proposers, proposed_in, approves, opposes, stances
ORDER BY approves - opposes DESC, approves DESC, toLower(s.name) ASC
"""

# Q40. The solutions proposed for an issue and its sub-issues, ranked by net support as Q4 ranks them.
ISSUE_STANCES = """
MATCH (i:Issue {key: $key})
OPTIONAL MATCH (child:Issue)-[:PART_OF]->(i)
WITH i, collect(child) AS children
UNWIND [i] + children AS x
MATCH (x)-[:HAVE_PROPOSED]->(s:Solution)
WITH DISTINCT s
WITH s, COUNT { (:Person)-[:APPROVE]->(s) } AS approves, COUNT { (:Person)-[:OPPOSE]->(s) } AS opposes
ORDER BY approves - opposes DESC, approves DESC, toLower(s.name) ASC
LIMIT $limit
""" + _SOLUTION_COLUMNS

# Q40, third form (GitHub issue 55): one solution, for a question asked on its own page.
ONE_SOLUTION_STANCES = """
MATCH (s:Solution {key: $key})
WITH s, COUNT { (:Person)-[:APPROVE]->(s) } AS approves, COUNT { (:Person)-[:OPPOSE]->(s) } AS opposes
""" + _SOLUTION_COLUMNS

# Q42. The solutions with the most net support in the whole record.
TOP_SOLUTIONS = """
MATCH (s:Solution)
WITH s, COUNT { (:Person)-[:APPROVE]->(s) } AS approves, COUNT { (:Person)-[:OPPOSE]->(s) } AS opposes
ORDER BY approves - opposes DESC, approves DESC, toLower(s.name) ASC
LIMIT $limit
""" + _SOLUTION_COLUMNS

# Q42, second form. The solutions most opposed in the whole record, so a question about opposition reads
# them even when its words find other issues.
TOP_OPPOSED = """
MATCH (s:Solution)
WITH s, COUNT { (:Person)-[:APPROVE]->(s) } AS approves, COUNT { (:Person)-[:OPPOSE]->(s) } AS opposes
WHERE opposes > 0
ORDER BY opposes DESC, approves ASC, toLower(s.name) ASC
LIMIT $limit
""" + _SOLUTION_COLUMNS

# Q42, the posts behind those solutions' stances (record scope), read by id and shaped like Q6 with the
# edit date. Their issues may not be among the three the question's words found.
POSTS_BY_IDS = """
MATCH (post:Post) WHERE post.id IN $ids
RETURN post.id AS id, post.text AS text, post.display_name AS display_name, post.anonymous AS anonymous,
       post.created_at AS created_at, post.seed AS seed, post.edited_at AS edited_at
"""

# One evidence edge's columns, shared by both forms of Q41: the evidence, what it is about, which way,
# the reading kept on the edge (Phase 2) and what the page says about itself; `answers` (issue 29) names the
# page a writer's own statement was written beside.
_EVIDENCE_COLUMNS = """
RETURN e.key AS key, e.name AS name, e.url AS url,
       e.source_checked_at IS NOT NULL AS source_known, e.source_type AS source_type,
       e.source_primary AS source_primary, e.source_published AS source_published,
       e.source_cites AS source_cites,
       CASE WHEN t:Issue THEN 'issue' WHEN t:Solution THEN 'solution' ELSE 'evidence' END AS target_kind,
       t.key AS target_key, t.name AS target_name, t.url AS target_url,
       toLower(type(r)) AS stance, r.check AS check, r.personal AS personal, r.post_id AS post_id,
       r.created_at AS created_at, r.answers AS answers
"""

# Q41, for an issue. Every evidence edge into the issue, its sub-issues or their solutions, then every
# edge from other evidence into that evidence (evidence on evidence, one step).
ISSUE_EVIDENCE = """
MATCH (i:Issue {key: $key})
OPTIONAL MATCH (child:Issue)-[:PART_OF]->(i)
WITH i, collect(child) AS children
WITH [i] + children AS issues
UNWIND issues AS x
OPTIONAL MATCH (x)-[:HAVE_PROPOSED]->(s:Solution)
WITH issues, collect(DISTINCT s) AS solutions
UNWIND issues + solutions AS t
MATCH (e:Evidence)-[:SUPPORTS|REFUTES]->(t)
WITH collect(DISTINCT t) + collect(DISTINCT e) AS targets
UNWIND targets AS t
MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(t)
WITH DISTINCT e, r, t
ORDER BY r.created_at
LIMIT $limit
""" + _EVIDENCE_COLUMNS

# Q41, for a solution (GitHub issue 55): every evidence edge into the solution, then every edge from other
# evidence into that evidence (one step), as the issue form reads them.
SOLUTION_EVIDENCE = """
MATCH (s:Solution {key: $key})
OPTIONAL MATCH (piece:Evidence)-[:SUPPORTS|REFUTES]->(s)
WITH s, collect(DISTINCT piece) AS pieces
UNWIND [s] + pieces AS t
MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(t)
WITH DISTINCT e, r, t
ORDER BY r.created_at
LIMIT $limit
""" + _EVIDENCE_COLUMNS

# Q41, for a piece of evidence (GitHub issue 55): the edges into it and its own edges out, as the record-wide
# form reads each top piece.
ONE_EVIDENCE = """
MATCH (top:Evidence {key: $key})
CALL (top) {
  MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(top)
  RETURN e, r, top AS t
  UNION
  MATCH (top)-[r:SUPPORTS|REFUTES]->(t)
  RETURN top AS e, r, t
}
WITH DISTINCT e, r, t
ORDER BY r.created_at
LIMIT $limit
""" + _EVIDENCE_COLUMNS

# Q41, record-wide. The evidence most supported by other evidence (then least refuted, then submitted
# by most posts), with the edges into it and its own edges out.
TOP_EVIDENCE = """
MATCH (top:Evidence)
WITH top, COUNT { (:Evidence)-[:SUPPORTS]->(top) } AS supported,
     COUNT { (:Evidence)-[:REFUTES]->(top) } AS refuted, COUNT { (:Person)-[:SUBMIT]->(top) } AS submitted
ORDER BY supported DESC, refuted ASC, submitted DESC, top.created_at ASC
LIMIT $limit
CALL (top) {
  MATCH (e:Evidence)-[r:SUPPORTS|REFUTES]->(top)
  RETURN e, r, top AS t
  UNION
  MATCH (top)-[r:SUPPORTS|REFUTES]->(t)
  RETURN top AS e, r, t
}
WITH DISTINCT e, r, t
ORDER BY r.created_at
""" + _EVIDENCE_COLUMNS


def issue_stances(key: str, limit: int = SOLUTION_LIMIT) -> list[dict[str, Any]]:
    """Q40."""
    return _read(ISSUE_STANCES, key=key, limit=limit, stance_limit=STANCE_LIMIT)


def solution_stances(key: str) -> list[dict[str, Any]]:
    """Q40's third form: the one solution, or no row."""
    return _read(ONE_SOLUTION_STANCES, key=key, stance_limit=STANCE_LIMIT)


def top_solutions(limit: int = 10) -> list[dict[str, Any]]:
    """Q42."""
    return _read(TOP_SOLUTIONS, limit=limit, stance_limit=STANCE_LIMIT)


def top_opposed(limit: int = 5) -> list[dict[str, Any]]:
    """Q42, second form."""
    return _read(TOP_OPPOSED, limit=limit, stance_limit=STANCE_LIMIT)


def posts_by_ids(ids: list[str]) -> list[dict[str, Any]]:
    """Q42, the posts behind the stances, by id."""
    return _read(POSTS_BY_IDS, ids=ids) if ids else []


def issue_evidence(key: str, limit: int = EDGE_LIMIT) -> list[dict[str, Any]]:
    """Q41 for an issue: one row per evidence edge, oldest first."""
    return _read(ISSUE_EVIDENCE, key=key, limit=limit)


def solution_evidence(key: str, limit: int = EDGE_LIMIT) -> list[dict[str, Any]]:
    """Q41 for a solution: one row per evidence edge, oldest first."""
    return _read(SOLUTION_EVIDENCE, key=key, limit=limit)


def one_evidence(key: str, limit: int = EDGE_LIMIT) -> list[dict[str, Any]]:
    """Q41 for a piece of evidence: one row per edge into or out of it, oldest first."""
    return _read(ONE_EVIDENCE, key=key, limit=limit)


def top_evidence(limit: int = EVIDENCE_LIMIT) -> list[dict[str, Any]]:
    """Q41 record-wide: one row per evidence edge into or out of the top evidence, oldest first."""
    return _read(TOP_EVIDENCE, limit=limit)
