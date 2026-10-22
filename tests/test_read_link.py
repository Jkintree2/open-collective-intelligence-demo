"""read_link: the arXiv second read, research papers, and PDFs with no text. No network."""

import json

import httpx
import pytest

from app import check
from app.check import confirmed
from app.config import Settings
from app.fetch_page import Page
from app.routes_evidence import read_link

SETTINGS = Settings("test", "test", "test", "neo4j://localhost:7687", "neo4j", "test", llm_api_key="private-test-key")
ABS = "https://arxiv.org/abs/1706.03762"
PAPER = "https://arxiv.org/pdf/1706.03762"
ABOUT = "Transformer models train quickly"
STATEMENT = "The Transformer paper says the base model trained in about 12 hours on eight GPUs."
ABSTRACT = Page("ok", ABS, "We propose a new simple network architecture, the Transformer, based solely on attention "
                "mechanisms. Our model achieves 28.4 BLEU after training for 3.5 days on eight GPUs.",
                "Attention Is All You Need", None, "2017-06-12")
FULL = Page("ok", PAPER, "We trained the base models for a total of 100,000 steps or 12 hours.\n"
            "Each training step took about 0.4 seconds.", None, None, "2024-04-10")
SOURCE = {"type": "other", "primary": False, "published": None}
UNCLEAR = {"verdict": "unclear", "quote": "", "reason": "The abstract does not give the base model's time.",
           "source": SOURCE, "suggested": {}}
SUPPORTS = {"verdict": "supports", "quote": "We trained the base models for a total of 100,000 steps or 12 hours.",
            "reason": "", "source": SOURCE, "suggested": {}}


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


def pages(table, seen):
    def fetcher(url, **kwargs):
        seen.append(url)
        return table[url]
    return fetcher


def no_backup(url, settings, **kwargs):
    raise AssertionError("not expected")


def run(url, table, *answers, seen, calls=None):
    return read_link(url, "Attention Is All You Need", ABOUT, STATEMENT, SETTINGS, writer_says="supports",
                     fetcher=pages(table, seen), backup=no_backup, transport=replies(*answers, calls=calls))


def test_when_the_abstract_does_not_settle_it_the_full_paper_is_read():
    seen, calls = [], []
    result = run(ABS, {ABS: ABSTRACT, PAPER: FULL}, UNCLEAR, SUPPORTS, seen=seen, calls=calls)
    assert seen == [ABS, PAPER] and len(calls) == 2
    assert result.verdict == "supports" and result.url == ABS
    assert result.quote == SUPPORTS["quote"]
    assert result.source == {"type": "research", "primary": True, "published": "2017-06-12"}
    assert result.usage == {"prompt_tokens": 2000, "completion_tokens": 200}
    # The card holds the abstract's link; the write path confirms the paper's reading under it.
    assert confirmed(ABS, ABOUT, STATEMENT, "supports", SUPPORTS["quote"]) is result


def test_an_abstract_that_settles_it_is_enough():
    seen = []
    quote = "Our model achieves 28.4 BLEU after training for 3.5 days on eight GPUs."
    result = run(ABS, {ABS: ABSTRACT}, {**SUPPORTS, "quote": quote}, seen=seen)
    assert seen == [ABS] and result.verdict == "supports" and result.quote == quote
    assert result.source["type"] == "research" and result.source["primary"] is True


def test_the_paper_unclear_too_keeps_the_abstracts_reading_unclear():
    seen = []
    result = run(ABS, {ABS: ABSTRACT, PAPER: FULL}, UNCLEAR, UNCLEAR, seen=seen)
    assert seen == [ABS, PAPER] and result.verdict == "unclear" and result.url == ABS


def test_an_abstract_that_cannot_be_opened_reads_the_paper():
    seen = []
    result = run(ABS, {ABS: Page("unread", ABS, reason="dns"), PAPER: FULL}, SUPPORTS, seen=seen)
    assert seen == [ABS, PAPER] and result.verdict == "supports" and result.url == ABS
    assert result.source["published"] == "2024-04-10"  # no abstract date to prefer


def test_an_unclear_page_elsewhere_is_read_once():
    url = "https://news.example.org/story"
    seen = []
    result = run(url, {url: Page("ok", url, ABSTRACT.text)}, UNCLEAR, seen=seen)
    assert seen == [url] and result.verdict == "unclear" and result.source["type"] == "other"


def test_a_pdf_with_no_text_says_so_and_is_never_kept():
    url = "https://gov.example.org/minutes.pdf"
    seen = []
    result = run(url, {url: Page("unread", url, reason="no_text")}, seen=seen)
    assert result.verdict == "notext"
    assert check.cache.get(check.cache_key(url, ABOUT, STATEMENT)).verdict == "notext"
    assert confirmed(url, ABOUT, STATEMENT, "notext", None) is None


def test_without_a_reading_service_nothing_is_read():
    seen = []
    result = read_link(ABS, "e", ABOUT, STATEMENT, Settings("t", "t", "t", "neo4j://x", "neo4j", "t"),
                       fetcher=pages({}, seen))
    assert result.verdict == "unchecked" and seen == []
