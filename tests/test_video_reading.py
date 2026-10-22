"""A YouTube video's reading: the quote's time, the channel's kind, no captions, and a pasted transcript that
is read like a page, never kept, and counts only when this process made the reading. No network."""

import importlib
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import check, confidence, fetch_video, routes_evidence
from app.auth import DailyLimit, KeyedLimit, MinuteBucket
from app.check import PASTED, Check, confirmed, kept_checks, source_words
from app.config import Settings
from app.extract import Candidates, CardPayload, resolve_payload
from app.fetch_page import Page
from app.fetch_video import caption_segments, pasted_segments, video_page
from app.routes_evidence import read_link

VIDEOS = Path(__file__).parent / "fixtures" / "videos"
URL = "https://www.youtube.com/watch?v=AbCdEfGhIj0"
ABOUT = "Pedestrian deaths in Lakeview"
STATEMENT = "Lower limits work: the Lakeview news video says pedestrian deaths fell by a third after the 20 mph limit."
SETTINGS = Settings("test", "test", "test", "neo4j://localhost:7687", "neo4j", "test", llm_api_key="private-test-key")
CAPTIONED = video_page(URL, caption_segments((VIDEOS / "captions.xml").read_text()), ABOUT,
                       "Lakeview lowered its speed limits", "A YouTube video by Lakeview Evening News.", "2024-03-05")
QUOTE = "The headline number: pedestrian deaths in Lakeview fell by a third"
SOURCE = {"type": "research", "primary": False, "published": None, "cites": None}
SUPPORTS = {"verdict": "supports", "quote": QUOTE, "claim_words": "", "reason": "", "source": SOURCE, "suggested": {}}
PASTE = (VIDEOS / "transcript.txt").read_text()
PASTE_QUOTE = "After six months, fifty six of the sixty one companies chose to keep the four day week."


@pytest.fixture(autouse=True)
def empty_cache():
    check.cache.clear()
    yield
    check.cache.clear()


def replies(*answers, calls=None):
    queue = list(answers)

    def respond(request):
        if calls is not None:
            calls.append(json.loads(request.content))
        usage = {"prompt_tokens": 1000, "completion_tokens": 100}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(queue.pop(0))}}], "usage": usage})
    return httpx.MockTransport(respond)


def video(page=CAPTIONED, seen=None):
    """A stand in for fetch_video.fetch: captions, or the writer's paste when one is given."""
    def fetcher(url, transcript=None, about="", **kwargs):
        if seen is not None:
            seen.append(transcript)
        return video_page(url, pasted_segments(transcript), about) if transcript else page
    return fetcher


def run(*answers, page=CAPTIONED, transcript=None, seen=None, about=ABOUT, statement=STATEMENT, calls=None):
    return read_link(URL, "Lakeview news report", about, statement, SETTINGS, writer_says="supports",
                     fetcher=video(page, seen), transcript=transcript, transport=replies(*answers, calls=calls))


def test_a_video_reading_carries_the_quotes_time_and_the_channels_kind():
    result = run(SUPPORTS)
    assert result.verdict == "supports" and result.quote == QUOTE and result.quote_at == "4:12"
    assert result.pasted is False and result.source["type"] == "other" and result.source["published"] == "2024-03-05"
    assert confirmed(URL, ABOUT, STATEMENT, "supports", QUOTE) is result


def test_captions_that_cannot_be_read_answer_nocaptions_and_are_never_kept():
    result = run(page=Page("unread", URL, reason="refused"))
    assert result.verdict == "nocaptions" and result.quote is None
    assert confirmed(URL, ABOUT, STATEMENT, "unread", None) is None


def test_a_pasted_transcript_is_read_afresh_and_says_it_was_pasted():
    seen = []
    assert run(page=Page("unread", URL, reason="no_captions"), seen=seen).verdict == "nocaptions"
    calls = []
    result = run({**SUPPORTS, "quote": PASTE_QUOTE}, transcript=PASTE, seen=seen, about="Four day week",
                 statement="A four day week works.", calls=calls)
    assert seen == [None, PASTE]
    assert result.verdict == "supports" and result.pasted is True and result.quote_at == "0:14"
    # Read exactly like a page: the same prompt, with the paste as the page's text.
    sent = json.loads(calls[0]["messages"][1]["content"])
    assert calls[0]["messages"][0]["content"] == check.SYSTEM_PROMPT and PASTE_QUOTE in sent["page"]["text"]
    assert "0:14" not in sent["page"]["text"]
    assert confirmed(URL, "Four day week", "A four day week works.", "supports", PASTE_QUOTE) is result


def test_a_quote_that_is_not_in_the_paste_is_unclear():
    result = run({**SUPPORTS, "quote": "Every company kept the four day week and revenue doubled."},
                 transcript=PASTE, about="Four day week", statement="A four day week works.")
    assert result.verdict == "unclear" and result.quote is None and result.pasted is True


def test_a_paste_without_times_has_no_time():
    plain = (VIDEOS / "transcript_plain.txt").read_text()
    quote = "So banning plastic straws, on its own, will not clean up the oceans."
    result = run({**SUPPORTS, "verdict": "refutes", "quote": quote}, transcript=plain, about="Ban plastic straws",
                 statement="Banning straws will not clean the oceans.")
    assert result.verdict == "refutes" and result.quote_at is None and result.pasted is True


def test_a_transcript_for_a_page_that_is_not_a_video_is_ignored():
    seen = []

    def page(url, **kwargs):
        seen.append(kwargs.get("transcript"))
        return Page("ok", url, "A survey of forty coastal towns found flooding days doubled since 2000.", "Survey")
    result = read_link("https://news.example.org/story", "Survey", "Coastal flooding", "Floods are worse.", SETTINGS,
                       fetcher=page, transcript="0:01 made up words", transport=replies(
                           {**SUPPORTS, "quote": "A survey of forty coastal towns found flooding days doubled since 2000."}))
    assert seen == [None] and result.pasted is False and result.quote_at is None


def resolved(about, url=URL, verdict="supports", quote=QUOTE):
    card = CardPayload.model_validate({"issues": [{"name": about}], "evidence": [
        {"name": "Lakeview news report", "url": url, "stance": "supports", "about": about,
         "check": {"verdict": verdict, "quote": quote, "quote_at": "9:99", "pasted": False}}]})
    return card, resolve_payload(card, Candidates.empty())


def test_the_write_path_takes_the_time_and_the_paste_from_this_processs_reading_only():
    run({**SUPPORTS, "quote": PASTE_QUOTE}, transcript=PASTE, about="Four day week", statement="A four day week works.")
    card, payload = resolved("Four day week", quote=PASTE_QUOTE)
    kept = kept_checks(card.evidence, payload.evidence, "A four day week works.")["lakeview news report"]
    assert kept["check"] == "supports" and kept["check_quote_at"] == "0:14" and kept["check_pasted"] is True
    check.cache.clear()  # a reading this process did not make is not kept, whatever the card says
    kept = kept_checks(card.evidence, payload.evidence, "A four day week works.")["lakeview news report"]
    assert kept == check.NO_CHECK


def test_an_edit_keeps_the_stored_time_and_paste():
    card, payload = resolved(ABOUT)
    stored = {("lakeview news report", make(ABOUT)): {"url": URL, "check": "supports", "check_quote": QUOTE,
                                                      "check_quote_at": "4:12", "check_pasted": True}}
    kept = kept_checks(card.evidence, payload.evidence, STATEMENT, stored)["lakeview news report"]
    assert kept["check_quote_at"] == "4:12" and kept["check_pasted"] is True


def make(name):
    from app.text import make_key
    return make_key(name)


@pytest.mark.parametrize("source, video, pasted, words", [
    ({"type": "news", "primary": False, "published": "2024-03-05"}, True, False,
     "A news video from March 2024. Secondary source."),
    ({"type": "organisation", "primary": True, "published": None}, True, False,
     "An organisation's video. Date not given. Primary source."),
    ({"type": "other", "primary": None, "published": "2025"}, True, True,
     "A video from 2025. Read from a transcript the writer pasted."),
    (None, True, True, "Read from a transcript the writer pasted."),
    ({"type": "news", "primary": False, "published": "2024-03-05"}, False, False,
     "A news report from March 2024. Secondary source."),
])
def test_the_source_line_for_a_video(source, video, pasted, words):
    assert source_words(source, today=date(2026, 10, 22), video=video, pasted=pasted) == words


def test_the_issue_page_says_where_in_the_video_and_that_a_transcript_was_pasted():
    base = {"target_kind": "issue", "target_key": "lakeview", "evidence_key": "clip", "stance": "SUPPORTS",
            "check": "supports", "check_quote": QUOTE, "source_known": True, "source_type": "news",
            "source_primary": False, "source_published": "2024-03-05"}
    rows = [dict(base, check_quote_at="4:12"), dict(base, check_quote="Other words from the paste here.",
                                                    check_pasted=True)]
    evidence = [{"key": "clip", "stance": "SUPPORTS", "url": URL}]
    confidence.annotate("lakeview", evidence, [], rows, today=date(2026, 10, 22))
    item = evidence[0]
    assert item["confidence"] == "A news video from March 2024. Secondary source."
    assert [(r["said"], r["pasted"]) for r in item["readings"]] == [
        ("The video says at 4:12", None), ("The transcript says", PASTED)]


def test_the_video_words_are_in_the_interface_doc():
    doc = (Path(__file__).resolve().parent.parent / "docs/planning/04_interface.md").read_text()
    for words in (check.PASTED, "news video", "organisation's video", "The video says at 4:12:",
                  "The transcript says:", "Read the transcript", "Reading the video…", "Reading the transcript…",
                  "Could not read this video's captions. Paste the transcript below and it will be read."):
        assert words in doc, words


@pytest.fixture
def api(monkeypatch):
    settings = Settings("test passphrase", "test secret", "test admin", "neo4j://localhost:7687", "neo4j", "test",
                        app_env="local", evidence_check_enabled=True, llm_api_key="offline test key")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
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

    def fake_read(url, evidence, about, text, settings, *, transcript=None, **kwargs):
        calls.append(transcript)
        if not transcript:
            result = Check("nocaptions", url)
        else:
            result = Check("supports", url, quote=PASTE_QUOTE, quote_at="0:14", pasted=True,
                           source={"type": "news", "primary": False, "published": "2024-03-05"})
        check.cache.put(check.cache_key(url, about, text), result)
        return result

    monkeypatch.setattr(routes_evidence, "read_link", fake_read)
    client = TestClient(main.app)
    client.post("/enter", data={"passphrase": "test passphrase"})
    yield client, calls
    client.close()


BODY = {"url": URL, "evidence": "Trial talk", "about": "Four day week", "text": "A four day week works.",
        "stance": "supports"}


def test_the_card_asks_for_a_paste_then_reads_it(api):
    client, calls = api
    first = client.post("/api/check-evidence", json=BODY).json()
    assert first["verdict"] == "nocaptions" and first["video"] is True and first["line"] is None
    second = client.post("/api/check-evidence", json={**BODY, "transcript": PASTE}).json()
    assert calls == [None, PASTE]  # the paste is read, not answered from the cache
    assert second["verdict"] == "supports" and second["quote_at"] == "0:14" and second["pasted"] is True
    assert second["line"] == "A news video from March 2024. Secondary source. " + PASTED
    assert PASTE not in json.dumps(second)


def test_a_paste_has_a_size_cap(api):
    client, calls = api
    too_long = client.post("/api/check-evidence", json={**BODY, "transcript": "a" * (fetch_video.MAX_TRANSCRIPT + 1)})
    assert too_long.status_code == 422 and calls == []


def test_a_paste_for_a_page_is_ignored(api):
    client, calls = api
    client.post("/api/check-evidence", json={**BODY, "url": "https://news.example.org/story", "transcript": "words"})
    assert calls == [None]


def test_a_paste_is_held_to_the_same_limits(api, monkeypatch):
    client, calls = api
    monkeypatch.setattr(routes_evidence, "person_limit", KeyedLimit(1, 600))
    assert client.post("/api/check-evidence", json={**BODY, "transcript": PASTE}).status_code == 200
    assert client.post("/api/check-evidence", json={**BODY, "transcript": PASTE}).status_code == 429
