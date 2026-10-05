"""Shared fixtures. Live tests run only against a disposable test Neo4j (7688 for A and B; C, D and E
each have their own port), never the development database on 7687 and never production; without
OCI_TEST_NEO4J_URI they are skipped."""

import os
from urllib.parse import urlsplit

import pytest

from app.config import Settings

LIVE_URI = os.environ.get("OCI_TEST_NEO4J_URI")


def pytest_collection_modifyitems(config, items):
    if LIVE_URI:
        return
    skip = pytest.mark.skip(reason="set OCI_TEST_NEO4J_URI to the disposable test Neo4j to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def live_graph():
    """`app.graph` on a wiped test database with the app's constraints, through the app's driver."""
    parts = urlsplit(LIVE_URI or "")
    if parts.hostname not in ("localhost", "127.0.0.1", "::1") or parts.port in (None, 7687):
        pytest.fail("live tests run only against the disposable test Neo4j on localhost, never port 7687")
    from app import graph
    settings = Settings("unused", "unused", "unused", LIVE_URI, "neo4j",
                        os.environ.get("OCI_TEST_NEO4J_PASSWORD", "testpass1"))
    graph.open_driver(settings)
    try:
        graph.driver().execute_query("MATCH (n) DETACH DELETE n", database_=graph.database())
        graph.ensure_constraints()
        # A new full-text index (sub-plan E) answers only once it is online.
        graph.driver().execute_query("CALL db.awaitIndexes(60)", database_=graph.database())
        yield graph
    finally:
        graph.close_driver()
