"""A PDF with no text: its notext answer never reaches the record; and with the flag off the card is
Phase 1's. No network, no database."""

import importlib
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import check, fetch_pdf
from app.auth import MinuteBucket
from app.check import NO_CHECK, kept_checks
from app.config import Settings
from app.extract import Candidates, CardPayload, resolve_payload
from app.routes_evidence import read_link

PDFS = Path(__file__).parent / "fixtures" / "pdfs"
URL = "https://council.example.org/minutes-2019.pdf"
STATEMENT = "The council minutes show flooding was discussed in 2019."
SETTINGS = Settings("test passphrase", "test secret", "test admin", "neo4j://localhost:7687", "neo4j", "test",
                    app_env="local", evidence_check_enabled=True, llm_api_key="offline test key")
CARD = {"issues": [{"name": "Coastal flooding"}],
        "evidence": [{"name": "Council minutes", "url": URL, "stance": "supports", "about": "Coastal flooding",
                      "check": {"verdict": "notext", "quote": None}}]}


@pytest.fixture(autouse=True)
def empty_cache():
    check.cache.clear()
    yield
    check.cache.clear()


def read_scanned():
    """The site's own reading of the scanned PDF, made as the route makes it, so it is in the cache."""
    scanned = (PDFS / "scanned.pdf").read_bytes()
    result = read_link(URL, "Council minutes", "Coastal flooding", STATEMENT, SETTINGS,
                       fetcher=lambda url, about="", **kwargs: fetch_pdf.page(scanned, url, about, None))
    assert result.verdict == "notext"
    return result


@pytest.fixture
def site(monkeypatch):
    holder = {"settings": SETTINGS}
    monkeypatch.setattr("app.config.get_settings", lambda: holder["settings"])
    monkeypatch.setattr("app.auth.get_settings", lambda: holder["settings"])
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "settings", SETTINGS)
    monkeypatch.setattr(main, "attempt_bucket", MinuteBucket(period=3600))
    monkeypatch.setattr(main, "post_spacing", type("Always", (), {"take": lambda self, key: True})())
    monkeypatch.setattr(main.graph, "candidates", lambda: Candidates.empty())
    for name, value in (("list_posts", lambda limit: []), ("post_structure", lambda ids: {}),
                        ("top_issues", lambda limit: [])):
        monkeypatch.setattr(main.graph, name, value)
    seen = []
    monkeypatch.setattr(main.graph, "merge_post", lambda *args, **kwargs: seen.append(kwargs) or "p1")
    client = TestClient(main.app)
    client.post("/enter", data={"passphrase": "test passphrase"})
    yield client, main, holder, seen
    client.close()


def test_notext_is_never_kept_for_the_write_path():
    read_scanned()
    card = CardPayload.model_validate(CARD)
    payload = resolve_payload(card, Candidates.empty())
    assert check.confirmed(URL, "Coastal flooding", STATEMENT, "notext", None) is None
    assert kept_checks(card.evidence, payload.evidence, STATEMENT) == {"council minutes": NO_CHECK}


def test_a_post_carrying_notext_is_stored_without_a_check(site):
    client, _, _, seen = site
    read_scanned()
    assert client.post("/api/posts", json={**CARD, "text": STATEMENT, "name": "Ada"}).status_code == 201
    assert seen[-1]["checks"] == {"council minutes": NO_CHECK}


def test_the_card_reads_links_only_with_the_flag_on(site, monkeypatch):
    client, main, holder, _ = site
    page = client.get("/").text
    assert "data-evidence-check" in page and "/static/evidence_check.js" in page
    off = replace(SETTINGS, evidence_check_enabled=False)
    holder["settings"] = off
    monkeypatch.setattr(main, "settings", off)
    page = client.get("/").text
    assert "data-evidence-check" not in page and "evidence_check.js" not in page
    assert client.post("/api/check-evidence", json={"url": URL, "about": "Coastal flooding"}).status_code == 404
