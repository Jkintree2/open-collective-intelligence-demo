"""Shared fixtures. Live tests run only against a disposable test Neo4j (7688 for A and B; C, D and E
each have their own port), never the development database on 7687 and never production; without
OCI_TEST_NEO4J_URI they are skipped."""

import importlib
import os
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app import accounts
from app.auth import DailyLimit, KeyedLimit, MinuteBucket, PostSpacing
from app.config import Settings
from app.extract import Candidates

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


# httpx files a cookie the TestClient's server sets under this domain. A cookie the test sets must
# use it too, or both are sent and Starlette reads the last one.
COOKIE_DOMAIN = "testserver.local"
# Every limiter in app.accounts, fresh and roomy for each test; raising=False because B adds some.
ACCOUNT_LIMITS = {
    "sign_in_per_minute": lambda: MinuteBucket(capacity=1000, period=60),
    "sign_in_per_address": lambda: KeyedLimit(1000, 60),
    "forgot_per_minute": lambda: MinuteBucket(capacity=1000, period=60),
    "link_per_address": lambda: KeyedLimit(1000, 3600),
    "entering_limit": lambda: KeyedLimit(1000, 3600),
}


@pytest.fixture
def member_app(monkeypatch):
    """The app with ACCOUNTS_ENABLED, stubbed reads and no database. `sign_in()` puts an account in
    the stubbed record and gives the client a valid member cookie for it."""
    settings = Settings("gate words", "member secret", "admin words", "neo4j://unused", "neo4j",
                        "test", app_env="local", accounts_enabled=True)
    for target in ("app.config.get_settings", "app.auth.get_settings"):
        monkeypatch.setattr(target, lambda: settings)
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "attempt_bucket", MinuteBucket(period=3600))
    monkeypatch.setattr(main, "reading_limit", DailyLimit())
    monkeypatch.setattr(main, "post_spacing", PostSpacing())
    for name, fresh in ACCOUNT_LIMITS.items():
        monkeypatch.setattr(accounts, name, fresh(), raising=False)
    monkeypatch.setattr(main.graph, "driver", lambda: pytest.fail("No offline test may open a database"))
    monkeypatch.setattr(main.graph, "list_posts", lambda limit: [])
    monkeypatch.setattr(main.graph, "post_structure", lambda ids: {})
    monkeypatch.setattr(main.graph, "top_issues", lambda limit: [])
    monkeypatch.setattr(main.graph, "list_issues", lambda: [])
    # `/?issue=` reads the issue's summary; with no driver open that read would be a 500.
    monkeypatch.setattr(main.graph, "issue_header", lambda key: None)
    monkeypatch.setattr(main.graph, "candidates", Candidates.empty)
    writes = []
    monkeypatch.setattr(main.graph, "merge_post", lambda *args, **kwargs: writes.append((args, kwargs)) or "post-id")
    record = {}
    monkeypatch.setattr("app.graph_accounts.member", lambda key: record.get(key), raising=False)
    client = TestClient(main.app, raise_server_exceptions=False)

    def set_cookie(value):
        client.cookies.set(accounts.MEMBER_COOKIE, value, domain=COOKIE_DOMAIN)

    def sign_in(key="acct:ada", name="Ada Lovelace", email="ada@example.org", admin=False,
                password_hash="scrypt$fixture-hash"):
        record[key] = {"key": key, "name": name, "email": email, "admin": admin, "password_hash": password_hash}
        set_cookie(accounts.make_member_cookie(key, password_hash, settings.secret_key))
        return record[key]

    yield SimpleNamespace(client=client, main=main, settings=settings, sign_in=sign_in, set_cookie=set_cookie,
                          accounts=record, writes=writes)
    client.close()
