"""The record layer's error handling with a stubbed driver: no database, no network."""

import traceback

import pytest
from neo4j.exceptions import ConstraintError

from app import graph_accounts
from app.graph_accounts import EmailTaken


class RefusingDriver:
    def execute_query(self, *args, **kwargs):
        raise ConstraintError("Node already exists with label `Person` and property `email` = 'bob@example.org'")


def test_email_taken_carries_nothing_from_the_driver_error(monkeypatch):
    """The driver's message names the clashing email or link; main.py logs tracebacks."""
    monkeypatch.setattr(graph_accounts, "driver", lambda: RefusingDriver())
    with pytest.raises(EmailTaken) as caught:
        graph_accounts._write_rows("CREATE (p:Person)")
    assert caught.value.__cause__ is None and caught.value.__suppress_context__ is True
    assert "bob@example.org" not in "".join(traceback.format_exception(caught.value))
