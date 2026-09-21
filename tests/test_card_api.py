import importlib
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import DailyLimit, MinuteBucket
from app.config import Settings
from app.extract import Candidates


@pytest.fixture
def api(monkeypatch):
    settings = Settings("test passphrase", "test secret", "test admin", "neo4j://localhost:7687", "neo4j", "test", app_env="local")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "attempt_bucket", MinuteBucket(period=3600))
    monkeypatch.setattr(main, "reading_limit", DailyLimit())
    candidates = Candidates(issues={"world": {"name": "World", "parent_key": None},
                                    "veto": {"name": "Veto", "parent_key": "world"}})
    monkeypatch.setattr(main.graph, "candidates", lambda: candidates)
    writes = []
    monkeypatch.setattr(main.graph, "merge_post", lambda *args, **kwargs: writes.append((args, kwargs)) or "post-id")
    monkeypatch.setattr(main.graph, "list_posts", lambda limit: [])
    monkeypatch.setattr(main.graph, "post_structure", lambda ids: {})
    monkeypatch.setattr(main.graph, "top_issues", lambda limit: [])
    client = TestClient(main.app)
    client.post("/enter", data={"passphrase": "test passphrase"})
    yield client, main, writes
    client.close()


def configure_reading(monkeypatch, main):
    """The minute and daily budgets belong to the reading service, so spending one needs a key."""
    monkeypatch.setattr(main, "settings", replace(main.settings, llm_api_key="offline test key"))
    monkeypatch.setattr(main.reading, "extract", lambda *args, **kwargs: None)


def test_unauthenticated_api_and_feed_remain_gated(api):
    client, _, writes = api
    client.cookies.clear()
    assert client.get("/api/candidates").status_code == 401
    assert client.post("/api/posts", json={"text": "Hello", "plain": True}).status_code == 401
    assert client.get("/feed", follow_redirects=False).status_code == 303
    assert not writes


def test_manual_anonymous_post_ignores_name_and_preserves_name_cookie(api):
    client, _, writes = api
    client.cookies.set("oci_name", "Remembered")
    result = client.post("/api/posts", json={"text": "Veto reform", "anonymous": True, "display_name": "Private name", "issues": [{"name": "Veto"}]})
    assert result.status_code == 201
    args, kwargs = writes[0]
    assert args[1:4] == (None, True, None)
    assert args[0].startswith("anon:")
    assert args[5].issues[0]["parent_key"] == "world"
    assert "oci_name" not in result.headers.get("set-cookie", "")
    assert "Private name" not in result.text
    assert kwargs["source"] == "manual"


def test_length_guard_precedes_reading_and_graph_and_seventh_call_is_limited(api, monkeypatch):
    client, main, writes = api
    monkeypatch.setattr(main.graph, "candidates", lambda: pytest.fail("unexpected database access"))
    for endpoint in ("extract", "posts", "preview"):
        assert client.post(f"/api/{endpoint}", json={"text": "x" * 4500}).status_code == 413
    monkeypatch.setattr(main.graph, "candidates", Candidates.empty)
    configure_reading(monkeypatch, main)
    for _ in range(6):
        result = client.post("/api/extract", json={"text": "Hello"})
        assert result.status_code == 200
        assert result.json()["source"] == "manual"
    assert client.post("/api/extract", json={"text": "Hello"}).status_code == 429
    assert not writes


def test_reading_without_a_key_is_never_limited_and_never_reads_the_record(api, monkeypatch):
    client, main, _ = api
    monkeypatch.setattr(main.graph, "candidates", lambda: pytest.fail("unexpected database access"))
    for _ in range(8):
        result = client.post("/api/extract", json={"text": "Hello"})
        assert result.status_code == 200
        assert result.json()["source"] == "manual"


def test_plain_statement_requires_explicit_choice_and_invalid_names_are_reported(api):
    client, _, writes = api
    assert client.post("/api/posts", json={"text": "Hello"}).status_code == 422
    assert client.post("/api/posts", json={"text": "Hello", "issues": [{"name": "!!!"}]}).status_code == 422
    assert client.post("/api/posts", json={"text": "Hello", "plain": True}).status_code == 201
    assert len(writes) == 1 and writes[0][0][5].is_empty


def test_preview_sentences_use_resolved_names_and_cleared_rows_are_removed(api):
    client, _, _ = api
    result = client.post("/api/preview", json={"text": "Veto reform", "display_name": "Tester", "issues": [{"name": "the veto."}]})
    assert result.json()["valid"]
    assert result.json()["sentences"] == ["Tester claims Veto"]
    assert result.json()["payload"]["issues"][0]["parent"] == "World"


def test_a_reading_result_is_kept_even_when_the_card_ends_up_manual(api):
    """05_extraction.md answers "it did something weird" from the post, so the raw reply stays."""
    client, _, writes = api
    result = client.post("/api/posts", json={"text": "Veto reform", "plain": True, "source": "manual",
                                             "extraction_raw": '{"found": false}', "model": "test-provider",
                                             "latency_ms": 12})
    assert result.status_code == 201
    _, kwargs = writes[0]
    assert kwargs["source"] == "manual"
    assert kwargs["extraction_raw"] == '{"found": false}'
    assert kwargs["model"] == "test-provider" and kwargs["latency_ms"] == 12


def test_feed_escapes_post_text(api, monkeypatch):
    client, main, _ = api
    monkeypatch.setattr(main.graph, "list_posts", lambda limit: [{"id": "one", "text": '<script>alert(1)</script>',
        "display_name": "Tester", "anonymous": False, "seed": False, "created_at": datetime.now(timezone.utc)}])
    response = client.get("/feed")
    assert response.status_code == 200
    assert "&lt;script&gt;" in response.text and "<script>" not in response.text


def test_daily_limit_is_separate_from_minute_refills():
    minute = MinuteBucket(capacity=1000)
    daily = DailyLimit(capacity=2)
    assert daily.take(minute, now=0)
    assert daily.take(minute, now=10)
    assert not daily.take(minute, now=120)
    assert daily.take(minute, now=86400)


def test_wrong_gate_attempt_and_reading_share_minute_bucket(api, monkeypatch):
    client, main, _ = api
    monkeypatch.setattr(main, "WRONG_PASSPHRASE_DELAY", 0)
    configure_reading(monkeypatch, main)
    client.post('/enter', data={"passphrase": "wrong"})
    for _ in range(5):
        assert client.post('/api/extract', json={"text": "Hello"}).status_code == 200
    assert client.post('/api/extract', json={"text": "Hello"}).status_code == 429


def test_empty_reading_result_is_manual_and_existing_result_preserves_badge(api, monkeypatch):
    from app.extract import CardPayload, Extraction, prepared_card

    client, main, _ = api
    empty = Extraction(CardPayload(found=False), '{"found":false}', 'test-provider', 10)
    monkeypatch.setattr(main.reading, "extract", lambda *args, **kwargs: empty)
    response = client.post('/api/extract', json={"text": "Hello"})
    assert response.json()["source"] == "manual"
    card = prepared_card(CardPayload.model_validate({"issues": [{"name": "the veto."}]}), main.graph.candidates())
    assert card.issues[0].existing and card.issues[0].parent == "World"


def test_html_form_still_posts_without_javascript_and_checks_untrimmed_length(api):
    client, _, writes = api
    response = client.post('/posts', data={"text": "A plain statement", "display_name": "Tester"}, follow_redirects=False)
    assert response.status_code == 303
    assert writes[0][0][4] == "A plain statement" and writes[0][0][5].is_empty
    assert client.post('/posts', data={"text": ' ' * 4500 + 'short'}).status_code == 413
    assert len(writes) == 1


def test_reading_passes_the_issue_key_to_the_reader(api, monkeypatch):
    client, main, _ = api
    seen = {}
    monkeypatch.setattr(main, "settings", replace(main.settings, llm_api_key="offline test key"))
    monkeypatch.setattr(main.reading, "extract", lambda text, name, candidates, settings, **kw: seen.update(kw) or None)
    client.post("/api/extract", json={"text": "Hello", "issue": "veto"})
    assert seen["writing_about"] == "veto"


def test_a_filled_card_posts_without_a_statement_and_stores_its_sentences(api):
    client, _, writes = api
    body = {"text": "", "display_name": "John", "issues": [{"name": "Veto"}],
            "solutions": [{"name": "Abolish the veto", "for_issue": "Veto", "stance": "approve"}]}
    preview = client.post("/api/preview", json=body)
    assert preview.status_code == 200 and preview.json()["valid"]
    assert client.post("/api/posts", json=body).status_code == 201
    args, _ = writes[0]
    assert args[4] == "John claims Veto. John proposes Abolish the veto. Veto has proposed Abolish the veto. John approves Abolish the veto."


def test_an_empty_card_with_no_statement_is_refused(api):
    client, _, writes = api
    assert client.post("/api/preview", json={"text": ""}).json()["valid"] is False
    assert client.post("/api/posts", json={"text": "", "plain": True}).status_code == 422
    assert client.post("/api/extract", json={"text": ""}).status_code == 422
    assert not writes
