"""Phase 3, ask the record: the answering call and the guard on its reply (ask.answer, ask.guard). No network."""

import json
import logging

import httpx
import pytest

from app import ask
from app.config import Settings
from app.principles import guiding_block

SETTINGS = Settings("p", "s", "a", "neo4j://x", "neo4j", "p", llm_api_key="test-key")
SOURCES = {
    "P1": ask.Source("P1", "post", "Ada Okafor", "2026-10-01", "Tax it.", "/issues/climate", "Climate"),
    "P2": ask.Source("P2", "post", "Anonymous", "2026-10-03", "Not a world tax.", "/issues/climate", "Climate"),
    "S1": ask.Source("S1", "solution", "Carbon tax", href="/issues/climate", issue="Climate"),
    "E1": ask.Source("E1", "evidence", "World Bank dashboard", href="/issues/climate", issue="Climate"),
}
DIGEST = ask.Digest('{"asked_about":"the issue Climate","issues":[]}', SOURCES, posts_in=2, posts_left_out=0,
                    issue_keys=["climate"])


def reply(*paragraphs, in_record=True):
    return {"in_record": in_record, "answer": [{"text": text, "sources": sources} for text, sources in paragraphs]}


def kept(*paragraphs, **kwargs):
    return ask.guard(reply(*paragraphs, **kwargs), DIGEST)


def test_a_source_outside_the_digest_is_dropped():
    paragraphs, counts = kept(("Ada wants a tax.", ["P1", "P9", "S7", "X1", 3, "p2"]))
    assert paragraphs == [{"text": "Ada wants a tax.", "sources": ["P1", "P2"]}]
    assert counts == {"paragraphs_dropped": 0, "sources_kept": 2, "sources_dropped": 4}


def test_a_paragraph_needs_a_post_unless_it_is_a_count_line():
    paragraphs, counts = kept(("Most people back the tax.", ["S1"]),
                              ("Approved by 4, opposed by 3, as of 17 October.", ["S1"]),
                              ("The dashboard is backed by 2 other pieces of evidence.", ["E1"]),
                              ("Only the solution, without a figure.", ["S1"]),
                              ("No evidence here is supported or refuted by other evidence.", ["E1"]),
                              ("Opposed by 3. " + "x" * 200, ["S1"]),
                              ("Ada and an anonymous writer disagree.", ["P1", "P2", "S1"]),
                              ("Nobody is cited.", []))
    assert [p["text"] for p in paragraphs] == ["Approved by 4, opposed by 3, as of 17 October.",
                                               "The dashboard is backed by 2 other pieces of evidence.",
                                               "No evidence here is supported or refuted by other evidence.",
                                               "Ada and an anonymous writer disagree."]
    assert counts["paragraphs_dropped"] == 4


def test_five_paragraphs_at_most_and_twelve_hundred_characters_in_order():
    five, counts = kept(*[(f"Point {n}.", ["P1"]) for n in range(1, 8)])
    assert [p["text"] for p in five] == [f"Point {n}." for n in range(1, 6)] and counts["paragraphs_dropped"] == 2
    long = "y" * 500
    paragraphs, _ = kept((long, ["P1"]), (long, ["P2"]), (long, ["P1"]), ("Short.", ["P2"]))
    assert [p["text"] for p in paragraphs] == [long, long]  # the third would pass 1,200; the rest go with it
    unbacked, _ = kept(("z" * 1100, []), ("Short and backed.", ["P1"]))
    assert [p["text"] for p in unbacked] == ["Short and backed."]  # a dropped paragraph counts for nothing


def test_not_in_the_record_or_nothing_left_is_empty():
    assert kept(("Mars has no posts.", ["P1"]), in_record=False)[0] == []
    assert kept(("Only an unknown source.", ["P9"]))[0] == []


def test_ids_in_the_text_become_names_or_go():
    paragraphs, _ = kept(("Ada (P1) and P2 differ on S1 [P1, P2]; E1 backs it.", ["P1"]))
    assert paragraphs[0]["text"] == "Ada and a post differ on Carbon tax; World Bank dashboard backs it."


def test_the_word_digest_never_reaches_a_reader():
    paragraphs, _ = kept(("No other posts in the digest say so; this Digest is short.", ["P1"]))
    assert paragraphs[0]["text"] == "No other posts in the record say so; this record is short."


def test_sources_are_numbered_in_the_order_first_cited():
    shown, sources = ask.numbered([{"text": "a", "sources": ["P2", "S1"]}, {"text": "b", "sources": ["P1", "P2"]}],
                                  DIGEST)
    assert shown == [{"text": "a", "refs": [1, 2]}, {"text": "b", "refs": [3, 1]}]
    assert [s.id for s in sources] == ["P2", "S1", "P1"]


@pytest.mark.parametrize("content", ["not json", "[]", '{"answer": []}', '{"in_record": "yes", "answer": []}',
                                     '{"in_record": true, "answer": "text"}', '{"in_record": true, "answer": [3]}',
                                     '{"in_record": true, "answer": [{"text": 1, "sources": []}]}'])
def test_a_reply_of_another_shape_is_refused(content):
    with pytest.raises(ValueError):
        ask.parse_answer(content)


def service(content, calls, usage=None):
    def respond(request):
        calls.append(json.loads(request.content))
        if content is None:
            return httpx.Response(500)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                         "usage": usage or {"prompt_tokens": 9000, "prompt_cache_hit_tokens": 7000,
                                                            "completion_tokens": 120}})
    return httpx.MockTransport(respond)


def test_the_call_carries_the_guiding_block_the_digest_and_only_earlier_questions(caplog):
    calls = []
    content = json.dumps(reply(("Ada wants a tax [P1].", ["P1"]), ("Approved by 4, as of 17 October.", ["S1"])))
    with caplog.at_level(logging.INFO, logger="oci"):
        result = ask.answer("And why?", ["q1", "q2", "", "q3", "q4"], DIGEST, SETTINGS, transport=service(content, calls),
                            request_id="r1")
    assert len(calls) == 1
    body = calls[0]
    system, user = body["messages"]
    assert system["role"] == "system" and system["content"].startswith("\n" + guiding_block() + "\n")
    assert system["content"] == ask.SYSTEM_PROMPT  # the same bytes every time, so the cache holds
    assert json.loads(user["content"]) == {"record": json.loads(DIGEST.text), "earlier_questions": ["q2", "q3", "q4"],
                                           "question": "And why?"}
    assert body["max_tokens"] == 700 and body["temperature"] == 0.1
    assert result.status == "answered" and result.message is None
    assert result.paragraphs == [{"text": "Ada wants a tax.", "refs": [1]},
                                 {"text": "Approved by 4, as of 17 October.", "refs": [2]}]
    assert [s.id for s in result.sources] == ["P1", "S1"] and result.partial is False
    line = next(json.loads(r.message) for r in caplog.records if '"event": "ask"' in r.message)
    assert line["prompt_tokens"] == 9000 and line["prompt_cache_hit_tokens"] == 7000 and line["paragraphs"] == 2
    assert line["history"] == 3 and "And why?" not in caplog.text and "Ada wants" not in caplog.text


def test_one_attempt_and_a_failure_says_so():
    calls = []
    result = ask.answer("Why?", [], DIGEST, SETTINGS, transport=service(None, calls))
    assert len(calls) == 1 and result.status == "failed"
    assert result.message == "The question could not be answered just now. Please try again in a minute."
    calls = []
    assert ask.answer("Why?", [], DIGEST, SETTINGS, transport=service("not json", calls)).status == "failed"
    assert len(calls) == 1


def test_an_empty_answer_and_a_partial_one():
    calls = []
    empty = ask.answer("Mars?", [], DIGEST, SETTINGS, transport=service(json.dumps(reply(in_record=False)), calls))
    assert empty.status == "empty" and empty.message == "The record does not say anything about this yet."
    partial_digest = ask.Digest(DIGEST.text, SOURCES, posts_in=2, posts_left_out=4)
    partial = ask.answer("Why?", [], partial_digest, SETTINGS,
                         transport=service(json.dumps(reply(("Ada wants a tax.", ["P1"]))), calls))
    assert partial.partial is True


def test_the_timeout_is_forty_seconds(monkeypatch):
    seen = {}
    monkeypatch.setattr(ask, "call_model", lambda messages, settings, **kw: seen.update(kw))
    ask.answer("Why?", [], DIGEST, SETTINGS)
    assert (seen["timeout"], seen["attempts"], seen["max_tokens"]) == (40, 1, 700)


def test_the_rules_have_no_dashes_where_a_reader_could_see_them():
    for line in (ask.EMPTY, ask.PARTIAL, ask.FAILED):
        assert "-" not in line and "\u2014" not in line and "\u2013" not in line
