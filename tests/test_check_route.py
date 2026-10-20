"""POST /api/check-evidence: behind the flag, gated, limited, and silent without a reading service."""

import importlib
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import check, routes_evidence
from app.auth import DailyLimit, KeyedLimit, MinuteBucket
from app.check import Check, source_words
from app.config import Settings
from app.extract import Candidates

BODY = {"url": "https://news.example.org/story", "evidence": "Survey", "about": "Coastal flooding",
        "text": "Floods are worse.", "stance": "supports"}


@pytest.fixture
def api(monkeypatch):
    settings = Settings("test passphrase", "test secret", "test admin", "neo4j://localhost:7687", "neo4j", "test",
                        app_env="local", evidence_check_enabled=True, llm_api_key="offline test key")
    holder = {"settings": settings}
    monkeypatch.setattr("app.config.get_settings", lambda: holder["settings"])
    monkeypatch.setattr("app.auth.get_settings", lambda: holder["settings"])
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "attempt_bucket", MinuteBucket(period=3600))
    monkeypatch.setattr(routes_evidence, "person_limit", KeyedLimit(1000, 600))
    monkeypatch.setattr(routes_evidence, "site_minute", MinuteBucket(capacity=1000, period=60))
    monkeypatch.setattr(routes_evidence, "site_daily", DailyLimit(capacity=1000))
    monkeypatch.setattr(routes_evidence.graph, "candidates", lambda: Candidates.empty())
    for name, value in (("list_posts", lambda limit: []), ("post_structure", lambda ids: {}),
                        ("top_issues", lambda limit: [])):
        monkeypatch.setattr(main.graph, name, value)
    calls = []

    def fake_check(url, evidence, about, text, settings, **kwargs):
        calls.append((url, evidence, about, text, kwargs["writer_says"]))
        return Check("supports", url, quote="Flooding days doubled since 2000 in forty towns.",
                     source={"type": "news", "primary": False, "published": "2024-03"})

    monkeypatch.setattr(routes_evidence.check, "check_evidence", fake_check)
    check.cache.clear()
    client = TestClient(main.app)
    client.post("/enter", data={"passphrase": "test passphrase"})
    yield client, holder, calls
    client.close()
    check.cache.clear()


def test_a_link_is_checked_and_described_in_words(api):
    client, _, calls = api
    response = client.post("/api/check-evidence", json=BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "supports" and body["line"] == "A news report from March 2024. Secondary source."
    assert "usage" not in body
    assert calls == [("https://news.example.org/story", "Survey", "Coastal flooding", "Floods are worse.", "supports")]


def test_off_without_the_flag(api):
    client, holder, calls = api
    holder["settings"] = replace(holder["settings"], evidence_check_enabled=False)
    assert client.post("/api/check-evidence", json=BODY).status_code == 404 and calls == []


def test_without_a_reading_service_nothing_is_read(api):
    client, holder, calls = api
    holder["settings"] = replace(holder["settings"], llm_api_key=None)
    assert client.post("/api/check-evidence", json=BODY).json()["verdict"] == "unchecked" and calls == []


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://example.org/x", "not a link", ""])
def test_a_link_that_is_not_http_is_not_read(api, url):
    client, _, calls = api
    assert client.post("/api/check-evidence", json={**BODY, "url": url}).json()["verdict"] == "unchecked"
    assert calls == []


def test_gated_and_same_origin_only(api):
    client, _, calls = api
    assert client.post("/api/check-evidence", json=BODY, headers={"Origin": "https://elsewhere.example"}).status_code == 403
    client.cookies.clear()
    assert client.post("/api/check-evidence", json=BODY).status_code == 401
    assert calls == []


def test_limited_per_browser_but_a_cached_link_is_free(api, monkeypatch):
    client, _, calls = api
    monkeypatch.setattr(routes_evidence, "person_limit", KeyedLimit(1, 600))
    assert client.post("/api/check-evidence", json=BODY).status_code == 200
    second = client.post("/api/check-evidence", json={**BODY, "url": "https://other.example.org/"})
    assert second.status_code == 429 and second.json()["message"] == routes_evidence.TOO_MANY
    check.cache.put(check.cache_key(BODY["url"], BODY["about"], BODY["text"]), Check("unclear", BODY["url"]))
    assert client.post("/api/check-evidence", json=BODY).json()["verdict"] == "unclear"


def test_oversized_fields_are_refused(api):
    client, _, calls = api
    assert client.post("/api/check-evidence", json={**BODY, "text": "x" * 4001}).status_code == 422
    assert calls == []


@pytest.mark.parametrize("source,words", [
    ({"type": "news", "primary": False, "published": "2024-03-14"}, "A news report from March 2024. Secondary source."),
    ({"type": "organisation", "primary": True, "published": "2019"}, "An organisation's page from 2019. Primary source."),
    ({"type": "government", "primary": None, "published": None}, "A government source. Date not given."),
    ({"type": "other", "primary": None, "published": "2021-13"}, "A page from 2021."),
    (None, None),
])
def test_source_words(source, words):
    assert source_words(source) == words


def test_route_copy_is_in_the_interface_doc():
    from pathlib import Path
    doc = (Path(__file__).resolve().parent.parent / "docs/planning/04_interface.md").read_text(encoding="utf-8")
    assert routes_evidence.TOO_MANY in doc
