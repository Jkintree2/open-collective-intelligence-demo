"""The evidence check: guard rails in code, not trust. No network."""

import json

import httpx
import pytest

from app import check
from app.check import check_evidence, confirmed
from app.config import Settings
from app.fetch_page import Page
from app.payload import Candidates

SETTINGS = Settings("test", "test", "test", "neo4j://localhost:7687", "neo4j", "test", llm_api_key="private-test-key")
URL = "https://news.example.org/story"
TEXT = ("A survey of forty coastal towns found that the number of flooding days has doubled since 2000.\n"
        "The authors say sea walls alone will not keep pace with rising seas.")
PAGE = Page("ok", URL, TEXT, "Coastal towns see record flooding", None, "2024-03-14")


@pytest.fixture(autouse=True)
def empty_cache():
    check.cache.clear()
    yield
    check.cache.clear()


def reply(data, calls=None):
    def respond(request):
        if calls is not None:
            calls.append(json.loads(request.content))
        content = data if isinstance(data, str) else json.dumps(data)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    return httpx.MockTransport(respond)


def page_of(page, seen=None):
    def fetcher(url, **kwargs):
        if seen is not None:
            seen.append((url, kwargs))
        return page
    return fetcher


def run(data, page=PAGE, **kwargs):
    kwargs.setdefault("transport", reply(data))
    return check_evidence(URL, "Forty town flooding survey", "Coastal flooding", "Floods are getting worse.",
                          SETTINGS, fetcher=page_of(page), **kwargs)


GOOD = {"verdict": "supports",
        "quote": "A survey of forty coastal towns found that the number of flooding days has doubled since 2000.",
        "reason": "The survey found flooding days doubled.",
        "source": {"type": "news", "primary": False, "published": "2024-03-14"},
        "suggested": {"issues": ["Sea walls not keeping pace"], "solutions": [], "evidence": []}}


def test_a_supporting_page_with_its_quote():
    result = run(GOOD)
    assert result.verdict == "supports" and result.quote.startswith("A survey of forty")
    assert result.source == {"type": "news", "primary": False, "published": "2024-03-14"}
    assert result.suggested["issues"] == [{"name": "Sea walls not keeping pace", "existing": False}]


def test_a_quote_not_on_the_page_turns_the_verdict_into_unclear():
    result = run({**GOOD, "verdict": "refutes", "quote": "Flooding has fallen sharply since 2000."})
    assert result.verdict == "unclear" and result.quote is None


def test_quote_matching_forgives_case_spacing_and_curly_quotes():
    page = Page("ok", URL, "The mayor said it\u2019s   the worst year on record for the harbour.")
    assert run({**GOOD, "quote": "the mayor said it's the worst year on record"}, page=page).verdict == "supports"


def test_a_tiny_quote_does_not_count():
    assert run({**GOOD, "quote": "flooding"}).verdict == "unclear"


@pytest.mark.parametrize("content", ["junk", json.dumps({"verdict": "maybe"}), json.dumps(["supports"])])
def test_a_bad_reply_is_unchecked_not_an_error(content):
    assert run(content).verdict == "unchecked"


def test_without_a_reading_service_nothing_is_fetched():
    seen = []
    result = check_evidence(URL, "x", "Coastal flooding", "s", Settings("t", "t", "t", "neo4j://x", "n", "p"),
                            fetcher=page_of(PAGE, seen))
    assert result.verdict == "unchecked" and seen == []


@pytest.mark.parametrize("status,verdict", [("unread", "unread"), ("unsupported", "unsupported")])
def test_a_page_that_cannot_be_read_is_not_sent_for_reading(status, verdict):
    calls = []
    result = run(GOOD, page=Page(status, URL, reason="x"), transport=reply(GOOD, calls))
    assert result.verdict == verdict and calls == []


def test_unknown_source_type_and_odd_values_are_cleaned():
    result = run({**GOOD, "source": {"type": "tabloid", "primary": "yes", "published": "last year"}},
                 page=Page("ok", URL, TEXT))
    assert result.source == {"type": "other", "primary": None, "published": None}


def test_the_page_date_wins_over_the_reply():
    assert run({**GOOD, "source": {"type": "news", "primary": None, "published": "1999"}}).source["published"] == "2024-03-14"


def test_suggestions_are_cleaned_capped_deduplicated_and_marked_existing():
    candidates = Candidates(solutions={"managed retreat": "Managed retreat"})
    data = {**GOOD, "suggested": {
        "issues": ["coastal flooding", "Insurance costs.", "insurance costs", "A", 7, "Erosion", "Storms", "Heat"],
        "solutions": ["managed retreat"], "evidence": ["Forty town flooding survey", "NOAA tide gauges"]}}
    result = run(data, candidates=candidates)
    assert [row["name"] for row in result.suggested["issues"]] == ["Insurance costs", "Erosion", "Storms"]
    assert result.suggested["solutions"] == [{"name": "Managed retreat", "existing": True}]
    assert [row["name"] for row in result.suggested["evidence"]] == ["NOAA tide gauges"]


def test_the_same_link_is_read_once_per_claim_and_statement():
    calls, seen = [], []
    for _ in range(3):
        check_evidence(URL, "s", "Coastal flooding", "Floods are getting worse.", SETTINGS,
                       fetcher=page_of(PAGE, seen), transport=reply(GOOD, calls))
    assert len(calls) == 1 and len(seen) == 1


def test_the_prompt_carries_the_page_and_the_claim_but_not_the_key():
    calls = []
    run(GOOD, transport=reply(GOOD, calls))
    user = json.loads(calls[0]["messages"][1]["content"])
    assert user["claim"] == "Coastal flooding" and user["page"]["text"] == TEXT
    assert "private-test-key" not in json.dumps(calls[0])


def test_confirmed_only_matches_a_reading_the_site_made():
    result = run(GOOD)
    statement = "Floods are getting worse."
    assert confirmed(URL, "Coastal flooding", statement, "supports", result.quote) is result
    assert confirmed(URL, "Coastal flooding", statement, "refutes", result.quote) is None
    assert confirmed(URL, "Coastal flooding", statement, "supports", "Something else entirely here.") is None
    assert confirmed(URL, "Sea walls", statement, "supports", result.quote) is None
    assert confirmed(URL, "Coastal flooding", "A different statement.", "supports", result.quote) is None
    assert confirmed("", "Coastal flooding", statement, "supports", result.quote) is None


def test_the_cache_forgets_the_oldest():
    small = check._Cache(size=2)
    for i in range(3):
        small.put((str(i), "", ""), check.Check("unclear", str(i)))
    assert small.get(("0", "", "")) is None and small.get(("2", "", "")) is not None


