"""POST /api/follow-ups: behind FOLLOW_UPS_ENABLED, gated, only new rows, and silent without a reading service."""

import importlib

import pytest
from fastapi.testclient import TestClient

from app import followups, routes_followups
from app.auth import DailyLimit, KeyedLimit, MinuteBucket
from app.config import Settings
from app.followups import MISSING_SOURCE, FollowUps

REAL = followups.follow_ups


ROWS = [{"row": "issue", "name": "Rent rises", "existing": False},
        {"row": "issue", "name": "Housing", "existing": True},
        {"row": "evidence", "name": "A survey", "existing": False, "url": None, "personal": False},
        {"row": "solution", "name": "  ", "existing": False}]


@pytest.fixture
def api(monkeypatch):
    def make(**changes):
        values = {"app_env": "local", "llm_api_key": "offline test key", "follow_ups_enabled": True, **changes}
        return Settings("test passphrase", "test secret", "test admin", "neo4j://localhost:7687", "neo4j", "test",
                        **values)
    holder = {"settings": make()}
    monkeypatch.setattr("app.config.get_settings", lambda: holder["settings"])
    monkeypatch.setattr("app.auth.get_settings", lambda: holder["settings"])
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "settings", holder["settings"])
    monkeypatch.setattr(main, "attempt_bucket", MinuteBucket(period=3600))
    monkeypatch.setattr(routes_followups, "person_limit", KeyedLimit(1000, 600))
    monkeypatch.setattr(routes_followups, "site_minute", MinuteBucket(capacity=1000, period=60))
    monkeypatch.setattr(routes_followups, "site_daily", DailyLimit(capacity=1000))
    for name, value in (("list_posts", lambda limit: []), ("post_structure", lambda ids: {}),
                        ("top_issues", lambda limit: [])):
        monkeypatch.setattr(main.graph, name, value)
    calls = []

    def fake(statement, rows, settings, **kwargs):
        calls.append((statement, [(row.row, row.name, row.url, row.personal) for row in rows], kwargs["limited"]()))
        return FollowUps([{"row": "evidence", "name": "A survey", "kind": "where", "text": MISSING_SOURCE, "fixed": True},
                          {"row": "issue", "name": "Rent rises", "kind": "who", "text": "Who is affected?", "fixed": False}])

    monkeypatch.setattr(routes_followups.followups, "follow_ups", fake)
    client = TestClient(main.app)
    client.post("/enter", data={"passphrase": "test passphrase"})
    yield client, holder, make, calls
    client.close()


def test_switched_off_the_route_is_not_found(api):
    client, holder, make, calls = api
    holder["settings"] = make(follow_ups_enabled=False)
    assert client.post("/api/follow-ups", json={"text": "x", "rows": ROWS}).status_code == 404
    assert calls == []


def test_only_new_named_rows_are_asked_about(api):
    client, _, _, calls = api
    response = client.post("/api/follow-ups", json={"text": "Rents doubled.", "rows": ROWS})
    assert response.status_code == 200
    assert [item["text"] for item in response.json()["questions"]] == [MISSING_SOURCE, "Who is affected?"]
    assert calls == [("Rents doubled.", [("issue", "Rent rises", None, False), ("evidence", "A survey", None, False)], False)]


def test_no_new_row_no_call(api):
    client, _, _, calls = api
    response = client.post("/api/follow-ups", json={"text": "Housing.", "rows": [ROWS[1]]})
    assert response.json() == {"questions": []} and calls == []


def test_a_person_past_the_limit_is_limited_not_refused(api, monkeypatch):
    client, _, _, calls = api
    monkeypatch.setattr(routes_followups, "person_limit", KeyedLimit(0, 600))
    response = client.post("/api/follow-ups", json={"text": "Rents doubled.", "rows": ROWS})
    assert response.status_code == 200 and calls[-1][2] is True


def test_without_the_passphrase_the_route_is_closed(api):
    client, _, _, calls = api
    client.cookies.clear()
    assert client.post("/api/follow-ups", json={"text": "x", "rows": ROWS}).status_code in (401, 403, 303)
    assert calls == []


def test_without_a_reading_service_the_real_call_gives_the_fixed_question(api, monkeypatch):
    client, holder, make, _ = api
    holder["settings"] = make(llm_api_key=None)
    monkeypatch.setattr(routes_followups.followups, "follow_ups", REAL)
    response = client.post("/api/follow-ups", json={"text": "Rents doubled.", "rows": ROWS})
    assert response.status_code == 200
    assert [item["text"] for item in response.json()["questions"]] == [MISSING_SOURCE]
