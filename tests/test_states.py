"""Session 4 state copy and offline client regressions; no database or model calls."""
import importlib
import re
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.auth import DailyLimit, MinuteBucket
from app.config import Settings
from app.extract import Candidates, CardPayload, Extraction


@pytest.fixture
def state_client(monkeypatch):
    settings = Settings("state pass", "state secret", "state admin", "neo4j://localhost:7687", "neo4j", "test", app_env="local")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "attempt_bucket", MinuteBucket())
    monkeypatch.setattr(main, "reading_limit", DailyLimit())
    monkeypatch.setattr(main.graph, "list_posts", lambda limit: [])
    monkeypatch.setattr(main.graph, "post_structure", lambda ids: {})
    monkeypatch.setattr(main.graph, "top_issues", lambda limit: [])
    monkeypatch.setattr(main.graph, "list_issues", lambda: [])
    monkeypatch.setattr(main.graph, "candidates", Candidates.empty)
    monkeypatch.setattr(main.graph, "merge_post", lambda *a, **kw: pytest.fail("unexpected database write"))
    # Deliberately do not enter TestClient: its lifespan would open a real driver.
    client = TestClient(main.app, raise_server_exceptions=False)
    client.post("/enter", data={"passphrase": "state pass"})
    yield client, main
    client.close()


def test_empty_pages_and_hidden_dictation_default(state_client):
    client, _ = state_client
    page = client.get("/")
    assert page.status_code == 200
    assert "Nothing here yet. Be the first to write something." in page.text
    assert 'id="dictate" class="quiet" aria-pressed="false" hidden' in page.text
    assert "No issues yet. Write something on the front page and it will appear here." in client.get("/issues").text


@pytest.mark.parametrize("asleep", [False, True])
def test_error_and_asleep_pages_use_exact_copy(state_client, monkeypatch, asleep):
    client, main = state_client
    def fail(limit):
        raise main.RecordAsleep("offline fixture") if asleep else RuntimeError("offline fixture")
    monkeypatch.setattr(main.graph, "list_posts", fail)
    response = client.get("/")
    assert response.status_code == (503 if asleep else 500)
    expected = "The record is asleep. John needs to press Play in the Neo4j console, and it wakes up in a few minutes." if asleep else "Something went wrong. Please try again in a minute."
    assert expected in response.text
    assert "offline fixture" not in response.text


@pytest.mark.parametrize("state, expected", [
    ("unavailable", "The reading service is not answering right now. You can fill in the form by hand, or try again in a minute."),
    ("not_found", "We could not find an issue, a claim, evidence or a solution in that. If you meant to make one, fill in the form below, or change the text and read it again."),
    ("english", "This demo reads English only for now."),
])
def test_reading_state_copy(state_client, monkeypatch, state, expected):
    client, main = state_client
    if state != "unavailable":
        result = Extraction(CardPayload(found=False, language_ok=state != "english"), "{}", "offline", 0)
        monkeypatch.setattr(main.reading, "extract", lambda *a, **kw: result)
    # Unavailable uses the real no-key path, which must never contact a provider.
    response = client.post("/api/extract", json={"text": "Hello"})
    assert response.status_code == 200
    assert response.json()["message"] == expected


def test_overlong_and_rate_limit_copy(state_client, monkeypatch):
    client, main = state_client
    response = client.post("/api/extract", json={"text": "x" * 4001})
    assert response.status_code == 413
    assert response.json()["message"] == "That is longer than this demo can read at once. Please shorten it to a few paragraphs."
    # The budget is the reading service's, so only a configured key spends it.
    monkeypatch.setattr(main, "settings", replace(main.settings, llm_api_key="offline test key"))
    monkeypatch.setattr(main.reading, "extract", lambda *a, **kw: None)
    for _ in range(6):
        assert client.post("/api/extract", json={"text": "Hello"}).status_code == 200
    response = client.post("/api/extract", json={"text": "Hello"})
    assert response.status_code == 429
    assert response.json()["message"] == "Too many requests. Please wait a minute or fill in the form by hand."


def test_client_recognition_and_request_races_offline():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable; run node --test tests/test_dictation.cjs when installed")
    result = subprocess.run([node, "--test", str(Path(__file__).with_name("test_dictation.cjs"))], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_write_about_shows_the_issue_summary_above_the_form(state_client, monkeypatch):
    client, main = state_client
    monkeypatch.setattr(main.graph, "candidates", lambda: Candidates(issues={"veto": {"name": "Security Council veto", "parent_key": "world"}, "world": {"name": "World", "parent_key": None}}))
    monkeypatch.setattr(main.graph, "issue_header", lambda key: {"key": "veto", "name": "Security Council veto", "parent_key": "world", "parent_name": "World", "children": []})
    monkeypatch.setattr(main.graph, "issue_solutions", lambda key: [{"key": "abolish", "name": "Abolish the veto", "proposers": 1, "approves": 1, "opposes": 0, "evidence": []}])
    monkeypatch.setattr(main.graph, "issue_evidence", lambda key: [{"key": "syria", "name": "Syria vetoes", "url": None, "stance": "SUPPORTS", "submitted_by": ["Seed"]}])
    page = client.get("/?issue=veto")
    assert page.status_code == 200
    assert "Already on record for Security Council veto" in page.text
    assert "Abolish the veto" in page.text and "I approve this" in page.text
    assert 'href="/issues/veto"' in page.text
    assert client.get("/?issue=nowhere").status_code == 200


def test_position_choices_for_one_solution_share_a_name_so_only_one_is_chosen(state_client, monkeypatch):
    client, main = state_client
    monkeypatch.setattr(main.graph, "issue_header", lambda key: {"key": "veto", "name": "Security Council veto", "parent_key": None, "parent_name": None, "children": []})
    monkeypatch.setattr(main.graph, "issue_solutions", lambda key: [
        {"key": "abolish", "name": "Abolish the veto", "proposers": 1, "approves": 0, "opposes": 0, "evidence": []},
        {"key": "widen", "name": "Widen the council", "proposers": 1, "approves": 0, "opposes": 0, "evidence": []},
    ])
    monkeypatch.setattr(main.graph, "issue_evidence", lambda key: [])
    page = client.get("/?issue=veto").text
    names = re.findall(r'<input type="radio" name="([^"]+)"', page)
    assert len(names) == 6
    # The three choices for one solution are one group; two solutions do not share a group.
    assert names[:3] == [names[0]] * 3 and names[3:] == [names[3]] * 3
    assert names[0] != names[3]


def test_issue_links_are_visible_and_sorts_are_labelled(state_client):
    client, _ = state_client
    page = client.get("/issues").text
    assert 'aria-label="Sort"' in page and 'Sort by' in page
    css = client.get("/static/app.css").text
    assert ".issue-card h2 a, .sub-issues a, .crumbs a { color: var(--accent); text-decoration: underline;" in css
