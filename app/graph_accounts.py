"""Account Cypher (03_schema.md, Phase 1, Q12 to Q22). Password hashes and link fields that these
queries return go to accounts.py and members.py only, never to a template or a log."""

from typing import Any

from app.graph_runtime import _read

# Q13. The signed-in account, on every request.
MEMBER = """
MATCH (p:Person {key: $key})
WHERE p.active AND p.accepted_at IS NOT NULL
RETURN p.key AS key, p.name AS name, p.email AS email, p.admin AS admin, p.password_hash AS password_hash
"""

# Q14. Sign in.
SIGN_IN = """
MATCH (p:Person {email: $email})
RETURN p.key AS key, p.password_hash AS password_hash, p.active AS active, p.accepted_at AS accepted_at
"""


def member(key: str) -> dict[str, Any] | None:
    rows = _read(MEMBER, key=key)
    return rows[0] if rows else None


def sign_in_row(email: str) -> dict[str, Any] | None:
    rows = _read(SIGN_IN, email=email)
    return rows[0] if rows else None
