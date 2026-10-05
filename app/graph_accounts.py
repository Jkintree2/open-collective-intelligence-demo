"""Account Cypher (03_schema.md, Phase 1, Q12 to Q22). Password hashes and link fields that these
queries return go to accounts.py and members.py only, never to a template or a log."""

from typing import Any

from neo4j.exceptions import ClientError, ConstraintError, ServiceUnavailable

from app.graph_runtime import RecordAsleep, _read, database, driver


class EmailTaken(Exception):
    """That email address already has an account (the person_email constraint)."""


def _write_rows(query: str, **params: Any) -> list[dict[str, Any]]:
    """A write that answers with rows."""
    try:
        result = driver().execute_query(query, params, database_=database())
    except ServiceUnavailable as exc:
        raise RecordAsleep(str(exc)) from exc
    except ConstraintError as exc:
        raise EmailTaken() from None  # the driver's message names the clashing value
    except ClientError as exc:
        # The person was deleted (an entry withdrawn) by another transaction while this one waited
        # for the lock it takes first: nothing to do, the same as no row. Neo4j 5 reports it as
        # Neo.ClientError.Statement.EntityNotFound; if the live test shows another code, match that.
        if (exc.code or "").endswith("EntityNotFound"):
            return []
        raise
    return [record.data() for record in result.records]


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


# Q12. Enter a person: the account, its link and ENTERED in one transaction.
ENTER_PERSON = """
MATCH (inviter:Person {key: $inviter_key})
WHERE inviter.active AND inviter.accepted_at IS NOT NULL
CREATE (p:Person {key: $key, name: $name, anonymous: false, seed: false,
                  email: $email, country: $country, postal_code: $postal_code,
                  admin: false, active: true, created_at: $now,
                  token_hash: $token_hash, token_purpose: 'invite', token_expires_at: $expires_at})
CREATE (inviter)-[:ENTERED {relationship: $relationship, agreed: true, created_at: $now}]->(p)
RETURN p.key AS key
"""

# The same inviter entering the same address moments ago: a double tap, not a duplicate.
RECENT_ENTRY = """
MATCH (:Person {key: $inviter_key})-[e:ENTERED]->(p:Person {email: $email})
WHERE e.created_at >= $since AND p.accepted_at IS NULL
RETURN p.key AS key
"""

# John's own account, the root: admin, no ENTERED, and no link (X3: make_admin.py sends nothing;
# "Forgot your password?" gives it its first link through Q17).
CREATE_ROOT = """
CREATE (p:Person {key: $key, name: $name, anonymous: false, seed: false,
                  email: $email, country: $country, postal_code: $postal_code,
                  admin: true, active: true, created_at: $now})
"""

# Q15. Open a link.
OPEN_LINK = """
MATCH (p:Person {token_hash: $token_hash})
OPTIONAL MATCH (inviter:Person)-[e:ENTERED]->(p)
RETURN p.key AS key, p.name AS name, p.email AS email, p.country AS country,
       p.postal_code AS postal_code, p.active AS active, p.accepted_at AS accepted_at,
       p.token_purpose AS purpose, p.token_expires_at AS expires_at,
       inviter.name AS inviter_name, e.relationship AS relationship
"""

# Lock first, then check (Q16, Q17, Q18, Q21; the trick Q23, Q24 and Q28 use): the no-op
# `SET p.key = p.key` takes the write lock before any condition is read, so a transaction that
# matched the person before another one committed waits for it, then checks what it left. The key
# never changes, so the no-op cannot write back a stale value (a no-op on token_hash could).

# Q16. Accept; the link is checked again after the lock, so a form sent twice accepts once.
ACCEPT = """
MATCH (p:Person {token_hash: $token_hash})
SET p.key = p.key
WITH p
WHERE p.token_hash = $token_hash AND p.token_purpose = 'invite' AND p.token_expires_at > $now AND p.active
SET p.name = $name, p.country = $country, p.postal_code = $postal_code,
    p.password_hash = $password_hash, p.accepted_at = $now,
    p.token_hash = null, p.token_purpose = null, p.token_expires_at = null
RETURN p.key AS key
"""

# Q17, sending an invitation again; the inviter's version also checks who entered the person.
RESEND_BY_INVITER = """
MATCH (:Person {key: $inviter_key})-[:ENTERED]->(p:Person {key: $key})
SET p.key = p.key
WITH p
WHERE p.accepted_at IS NULL AND p.active
SET p.token_hash = $token_hash, p.token_purpose = 'invite', p.token_expires_at = $expires_at
WITH p
OPTIONAL MATCH (inviter:Person)-[e:ENTERED]->(p)
RETURN p.email AS email, p.name AS name, inviter.name AS inviter_name, e.relationship AS relationship
"""
RESEND_ANY = """
MATCH (p:Person {key: $key})
SET p.key = p.key
WITH p
WHERE p.accepted_at IS NULL AND p.active
SET p.token_hash = $token_hash, p.token_purpose = 'invite', p.token_expires_at = $expires_at
WITH p
OPTIONAL MATCH (inviter:Person)-[e:ENTERED]->(p)
RETURN p.email AS email, p.name AS name, inviter.name AS inviter_name, e.relationship AS relationship
"""

# Q17, the "Forgot your password?" form: an accepted, active account gets a password link; someone
# entered but not yet accepted gets a fresh invitation link; anyone else gets nothing. Locked first,
# so an accept committing meanwhile is seen and no invitation link lands on an account.
FORGOT = """
MATCH (p:Person {email: $email})
SET p.key = p.key
WITH p
WHERE p.active
WITH p, CASE WHEN p.accepted_at IS NULL THEN 'invite' ELSE 'reset' END AS purpose
SET p.token_hash = $token_hash, p.token_purpose = purpose,
    p.token_expires_at = CASE purpose WHEN 'invite' THEN $invite_expires_at ELSE $reset_expires_at END
WITH p, purpose
OPTIONAL MATCH (inviter:Person)-[e:ENTERED]->(p)
RETURN p.email AS email, p.name AS name, purpose, inviter.name AS inviter_name, e.relationship AS relationship
"""

# Q18. Choose a new password through a link. Locked first, then the link checked again, so the
# same link sent from two tabs sets one password.
RESET_PASSWORD = """
MATCH (p:Person {token_hash: $token_hash})
SET p.key = p.key
WITH p
WHERE p.token_hash = $token_hash AND p.token_purpose = 'reset' AND p.token_expires_at > $now
  AND p.active AND p.accepted_at IS NOT NULL
SET p.password_hash = $password_hash,
    p.token_hash = null, p.token_purpose = null, p.token_expires_at = null
RETURN p.key AS key
"""

# Q19. Change password while signed in; a pending password link stops working too.
SET_PASSWORD = """
MATCH (p:Person {key: $key})
SET p.password_hash = $password_hash,
    p.token_hash = null, p.token_purpose = null, p.token_expires_at = null
"""

# Q19a. Who entered this account (the account page); John's root has no entry and no row.
WHO_ENTERED = """
MATCH (inviter:Person)-[e:ENTERED]->(:Person {key: $key})
RETURN inviter.name AS inviter_name, e.relationship AS relationship, e.created_at AS entered_at
"""

# Q20. People one has entered.
ENTERED_BY = """
MATCH (me:Person {key: $key})-[e:ENTERED]->(p:Person)
RETURN p.key AS key, p.name AS name, p.email AS email, e.relationship AS relationship,
       e.created_at AS entered_at, p.accepted_at AS accepted_at, p.active AS active,
       p.token_purpose AS purpose, p.token_expires_at AS expires_at
ORDER BY e.created_at DESC
"""

# Q21. Withdraw an entry never accepted; the person has nothing but the ENTERED edge. Locked
# first, so an accept that commits meanwhile wins and the withdrawal finds an accepted account.
WITHDRAW_BY_INVITER = """
MATCH (:Person {key: $inviter_key})-[:ENTERED]->(p:Person {key: $key})
SET p.key = p.key
WITH p
WHERE p.accepted_at IS NULL AND COUNT { (p)--() } = 1
DETACH DELETE p
RETURN count(*) AS withdrawn
"""
WITHDRAW_ANY = """
MATCH (:Person)-[:ENTERED]->(p:Person {key: $key})
SET p.key = p.key
WITH p
WHERE p.accepted_at IS NULL AND COUNT { (p)--() } = 1
DETACH DELETE p
RETURN count(*) AS withdrawn
"""


def enter_person(*, inviter_key: str, key: str, name: str, email: str, country: str, postal_code: str,
                 relationship: str, token_hash: str, expires_at, now) -> bool:
    return bool(_write_rows(ENTER_PERSON, inviter_key=inviter_key, key=key, name=name, email=email,
                            country=country, postal_code=postal_code, relationship=relationship,
                            token_hash=token_hash, expires_at=expires_at, now=now))


def recent_entry(inviter_key: str, email: str, since) -> str | None:
    rows = _read(RECENT_ENTRY, inviter_key=inviter_key, email=email, since=since)
    return rows[0]["key"] if rows else None


def create_root(*, key: str, name: str, email: str, country: str, postal_code: str, now) -> None:
    _write_rows(CREATE_ROOT, key=key, name=name, email=email, country=country, postal_code=postal_code, now=now)


def open_link(token_hash: str) -> dict[str, Any] | None:
    rows = _read(OPEN_LINK, token_hash=token_hash)
    return rows[0] if rows else None


def accept(token_hash: str, *, name: str, country: str, postal_code: str, password_hash: str, now) -> str | None:
    rows = _write_rows(ACCEPT, token_hash=token_hash, name=name, country=country, postal_code=postal_code,
                       password_hash=password_hash, now=now)
    return rows[0]["key"] if rows else None


def resend_invitation(key: str, token_hash: str, expires_at, inviter_key: str | None = None) -> dict[str, Any] | None:
    query = RESEND_ANY if inviter_key is None else RESEND_BY_INVITER
    rows = _write_rows(query, key=key, token_hash=token_hash, expires_at=expires_at, inviter_key=inviter_key)
    return rows[0] if rows else None


def entered_by(inviter_key: str) -> list[dict[str, Any]]:
    return _read(ENTERED_BY, key=inviter_key)


def withdraw(key: str, inviter_key: str | None = None) -> bool:
    query = WITHDRAW_ANY if inviter_key is None else WITHDRAW_BY_INVITER
    rows = _write_rows(query, key=key, inviter_key=inviter_key)
    return bool(rows and rows[0]["withdrawn"])


def forgot(email: str, token_hash: str, invite_expires_at, reset_expires_at) -> dict[str, Any] | None:
    rows = _write_rows(FORGOT, email=email, token_hash=token_hash,
                       invite_expires_at=invite_expires_at, reset_expires_at=reset_expires_at)
    return rows[0] if rows else None


def reset_password(token_hash: str, password_hash: str, now) -> str | None:
    rows = _write_rows(RESET_PASSWORD, token_hash=token_hash, password_hash=password_hash, now=now)
    return rows[0]["key"] if rows else None


def set_password(key: str, password_hash: str) -> None:
    _write_rows(SET_PASSWORD, key=key, password_hash=password_hash)


def who_entered(key: str) -> dict[str, Any] | None:
    rows = _read(WHO_ENTERED, key=key)
    return rows[0] if rows else None
