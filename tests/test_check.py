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


def no_backup(url, settings, **kwargs):
    raise AssertionError("the backup reader was not expected here")


def run(data, page=PAGE, **kwargs):
    kwargs.setdefault("transport", reply(data))
    kwargs.setdefault("backup", no_backup)
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
    assert result.source == {"type": "news", "primary": False, "published": "2024-03-14", "cites": None}
    assert result.suggested["issues"] == [{"name": "Sea walls not keeping pace", "existing": False}]


def test_a_quote_not_on_the_page_turns_the_verdict_into_unclear():
    result = run({**GOOD, "verdict": "refutes", "quote": "Flooding has fallen sharply since 2000."})
    assert result.verdict == "unclear" and result.quote is None


def test_quote_matching_forgives_case_spacing_and_curly_quotes():
    page = Page("ok", URL, "The mayor said it\u2019s   the worst year on record for the harbour.")
    assert run({**GOOD, "quote": "the mayor said it's the worst year on record"}, page=page).verdict == "supports"


def test_quote_matching_skips_footnote_marks():
    # Wikipedia's text is full of "[4][5]"; the reading quotes the sentence without them, or with them.
    page = Page("ok", URL, "The modern-day rise in global temperatures[4] is driven by human activities,[5] "
                           "especially fossil fuel burning.[6][citation needed]")
    for quote in ("The modern-day rise in global temperatures is driven by human activities, especially fossil fuel burning.",
                  "The modern-day rise in global temperatures[4] is driven by human activities,[5] especially fossil fuel burning.[6]"):
        check.cache.clear()
        result = run({**GOOD, "quote": quote}, page=page)
        assert result.verdict == "supports" and "[" not in result.quote


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


@pytest.mark.parametrize("status,reason,verdict", [("unread", "address", "unread"), ("unsupported", "type", "unsupported")])
def test_a_page_that_cannot_be_read_is_not_sent_for_reading(status, reason, verdict):
    calls = []
    result = run(GOOD, page=Page(status, URL, reason=reason), transport=reply(GOOD, calls))
    assert result.verdict == verdict and calls == []


def test_unknown_source_type_and_odd_values_are_cleaned():
    result = run({**GOOD, "source": {"type": "tabloid", "primary": "yes", "published": "last year"}},
                 page=Page("ok", URL, TEXT))
    assert result.source == {"type": "other", "primary": None, "published": None, "cites": None}


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
    # The writer may tidy the statement after the link was read: the same page, read for the same claim.
    assert confirmed(URL, "Coastal flooding", "A different statement.", "supports", result.quote) is result
    assert confirmed("https://other.example.org/", "Coastal flooding", statement, "supports", result.quote) is None
    assert confirmed("", "Coastal flooding", statement, "supports", result.quote) is None


def test_the_cache_forgets_the_oldest():
    small = check._Cache(size=2)
    for i in range(3):
        small.put((str(i), "", ""), check.Check("unclear", str(i)))
    assert small.get(("0", "", "")) is None and small.get(("2", "", "")) is not None




def test_a_page_our_reader_could_not_open_goes_to_the_backup_reader():
    asked = []

    def backup(url, settings, **kwargs):
        asked.append(url)
        return PAGE

    result = run(GOOD, page=Page("unread", URL, reason="http"), backup=backup)
    assert asked == [URL] and result.verdict == "supports"


@pytest.mark.parametrize("change", [{"deepseek_fetch": False}, {"llm_base_url": "https://api.other.example"}])
def test_the_backup_reader_is_off_with_its_switch_or_another_provider(change):
    from dataclasses import replace
    result = check_evidence(URL, "s", "Coastal flooding", "x", replace(SETTINGS, **change),
                            fetcher=page_of(Page("unread", URL, reason="http")), backup=no_backup, transport=reply(GOOD))
    assert result.verdict == "unread"


def test_a_reference_work_is_dated_by_its_last_update():
    page = Page("ok", URL, TEXT, "Flat Earth", None, "2001-12-06", modified="2026-10-17")
    reference = {**GOOD, "source": {"type": "reference", "primary": False, "published": "2001"}}
    assert run(reference, page=page).source["published"] == "2026-10-17"
    check.cache.clear()
    assert run(GOOD, page=page).source["published"] == "2001-12-06"   # a news report keeps its first date


def test_a_long_page_is_cut_around_the_writers_words_and_the_reader_names_the_site():
    seen = []
    settings = Settings("test", "test", "test", "neo4j://localhost:7687", "neo4j", "test", llm_api_key="k",
                        site_url="https://oci.example.org")
    check_evidence(URL, "Forty town survey", "Coastal flooding", "Flooding days doubled in forty towns.", settings,
                   fetcher=page_of(PAGE, seen), transport=reply(GOOD), backup=no_backup)
    assert seen[0][1]["about"] == "Forty town survey Coastal flooding Flooding days doubled in forty towns."
    assert "https://oci.example.org" in seen[0][1]["agent"]


def test_the_prompt_asks_for_the_writers_own_words_to_be_borne_out():
    # Audrey Tang, 21 October: "80% became law, which proves" was never checked against the page.
    assert "bear out what the writer says it shows" in check.SYSTEM_PROMPT
    prompt = " ".join(check.SYSTEM_PROMPT.split())
    assert 'say in "reason" exactly what the page does not say' in prompt
    # Revision round, 22 October: going further than the page is partly, not unclear.
    assert "answer partly" in prompt and '"claim_words"' in prompt


def test_the_prompt_reads_the_claim_alone_first_and_a_denial_backed_by_the_page_is_refutes():
    # PR 16 was reverted for reading a page that backs a writer's denial as supports (22 October 2026).
    prompt = " ".join(check.SYSTEM_PROMPT.split())
    assert "Step 1, the claim alone. Ignore the statement." in prompt
    assert "only when step 1 says supports" in prompt
    assert "When step 1 says refutes, answer refutes, whatever the writer's words say." in prompt
    assert "the page agreeing with the writer is not the page supporting the claim" in prompt
    assert "that is supports" not in prompt


# Revision round: partly agrees, the writer's own sentence, and whether the page names its sources.
STATEMENT = "Floods are getting worse. The survey of forty towns shows flooding days tripled since 2000."
PARTLY = {**GOOD, "verdict": "partly", "claim_words": "The survey of forty towns shows flooding days tripled since 2000.",
          "reason": "The page says flooding days doubled, not tripled.",
          "source": {"type": "news", "primary": False, "published": "2024-03-14", "cites": True}}


def run_with(data, statement=STATEMENT, page=PAGE):
    return check_evidence(URL, "Forty town flooding survey", "Coastal flooding", statement, SETTINGS,
                          fetcher=page_of(page), backup=no_backup, transport=reply(data))


def test_a_partly_reading_keeps_its_quote_reason_and_the_writers_sentence():
    result = run_with(PARTLY)
    assert result.verdict == "partly" and result.quote.startswith("A survey of forty")
    assert result.claim == "The survey of forty towns shows flooding days tripled since 2000."
    assert result.reason == "The page says flooding days doubled, not tripled."
    assert result.source["cites"] is True
    assert result.as_json()["claim"] == result.claim
    assert confirmed(URL, "Coastal flooding", STATEMENT, "partly", result.quote) is result


def test_a_partly_reading_whose_quote_is_not_on_the_page_is_unclear():
    result = run_with({**PARTLY, "quote": "Flooding days tripled since 2000."})
    assert result.verdict == "unclear" and result.quote is None


def test_the_writers_sentence_must_be_in_the_statement():
    assert run_with({**PARTLY, "claim_words": "Flooding is the worst it has ever been anywhere."}).claim is None
    check.cache.clear()
    assert run_with({**PARTLY, "claim_words": ""}).claim is None
    check.cache.clear()
    assert run_with({**PARTLY, "claim_words": 7}).claim is None
    check.cache.clear()
    # Spacing and curly quotes are forgiven, as for the page's quote.
    assert run_with({**PARTLY, "claim_words": "the survey of  forty towns shows flooding days tripled"}).claim == \
        "the survey of forty towns shows flooding days tripled"


def test_odd_cites_values_become_null():
    for odd in ("yes", 1, None):
        check.cache.clear()
        assert run_with({**PARTLY, "source": {**PARTLY["source"], "cites": odd}}).source["cites"] is None


def test_the_writers_supports_or_refutes_is_never_sent_to_the_reading():
    # Told only to ignore it, the reading still followed it: Hans Rosling's talk, cited by a writer who chose
    # refutes, came back as supports with a reason saying it argues against the claim (C30, 22 October 2026).
    page = check.Page("ok", "https://example.org", "Text of the page that is long enough to read.", "Title")
    for writer_says in ("supports", "refutes"):
        sent = check.build_messages(page, "Evidence", "A claim", "A statement.", writer_says)
        assert "writer_says" not in sent[1]["content"] and "writer_says" not in sent[0]["content"]
