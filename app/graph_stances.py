"""One stance per person and solution (03_schema.md, Phase 1, Q23 and D7)."""

from datetime import datetime
from typing import Any

from neo4j.exceptions import ServiceUnavailable

from app.graph import OPPOSITE_STANCE, STANCE_TYPES
from app.graph_runtime import RecordAsleep, database, driver

# Both write locks are taken before anything is read, the same trick as MERGE_PART_OF, so two
# quick presses from two tabs are applied one after the other. {stance} and {other} come from
# STANCE_TYPES and OPPOSITE_STANCE only.
SET_STANCE = """
MATCH (p:Person {key: $person_key}), (s:Solution {key: $solution_key})
SET p.key = p.key, s.key = s.key
WITH p, s
OPTIONAL MATCH (p)-[old:{other}]->(s)
DELETE old
WITH DISTINCT p, s
MERGE (p)-[r:{stance}]->(s)
ON CREATE SET r.source = 'click', r.anonymous = false, r.created_at = $now
RETURN type(r) AS stance
"""

WITHDRAW_STANCE = """
MATCH (p:Person {key: $person_key}), (s:Solution {key: $solution_key})
SET p.key = p.key, s.key = s.key
WITH p, s
OPTIONAL MATCH (p)-[r:APPROVE|OPPOSE]->(s)
DELETE r
RETURN count(*) AS rows
"""

# Read inside the same transaction, so the answer is what this change left.
SOLUTION_COUNTS = """
MATCH (s:Solution {key: $solution_key})
OPTIONAL MATCH (pa:Person)-[:APPROVE]->(s)
WITH s, count(DISTINCT pa) AS approves
OPTIONAL MATCH (po:Person)-[:OPPOSE]->(s)
WITH s, approves, count(DISTINCT po) AS opposes
OPTIONAL MATCH (:Person {key: $person_key})-[mine:APPROVE|OPPOSE]->(s)
RETURN approves, opposes, head(collect(type(mine))) AS my_stance
"""


def set_stance(person_key: str, solution_key: str, stance: str | None, now: datetime) -> dict[str, Any] | None:
    """`stance` is 'approve', 'oppose' or None to withdraw. One transaction. Returns the solution's
    counts and the person's stance afterwards, or None when the person or solution is missing."""
    params = {"person_key": person_key, "solution_key": solution_key}

    def work(tx: Any) -> dict[str, Any] | None:
        if stance is None:
            found = tx.run(WITHDRAW_STANCE, **params).single()["rows"]
        else:
            rel = STANCE_TYPES[stance]
            query = SET_STANCE.replace("{stance}", rel).replace("{other}", OPPOSITE_STANCE[rel])
            found = tx.run(query, now=now, **params).single()
        if not found:
            return None
        row = tx.run(SOLUTION_COUNTS, **params).single()
        return {"approves": row["approves"], "opposes": row["opposes"], "my_stance": row["my_stance"]}

    try:
        with driver().session(database=database()) as session:
            return session.execute_write(work)
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
