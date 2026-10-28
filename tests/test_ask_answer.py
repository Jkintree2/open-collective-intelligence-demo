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
                              ("One solution is to ban cars.", ["S1"]),
                              ("Opposed by 3. " + "x" * 200, ["S1"]),
                              ("Ada and an anonymous writer disagree.", ["P1", "P2", "S1"]),
                              ("Nobody is cited.", []))
    assert [p["text"] for p in paragraphs] == ["Approved by 4, opposed by 3, as of 17 October.",
                                               "The dashboard is backed by 2 other pieces of evidence.",
                                               "No evidence here is supported or refuted by other evidence.",
                                               "Ada and an anonymous writer disagree."]
    assert counts["paragraphs_dropped"] == 5


def test_a_number_word_counts_only_beside_what_it_counts():
    """The final review: "One solution is to ban cars." on an S id alone is a claim, not a count."""
    for text in ("One solution is to ban cars.", "No reason is given for it.", "None of this is settled."):
        assert kept((text, ["S1"]))[0] == [], text
    for text in ("No evidence here is supported or refuted by other evidence.", "Three people oppose it.",
                 "Two other pieces of evidence back it.", "Opposed by none, approved by two.",
                 "Approved by 4, opposed by 3, as of 17 October."):
        assert [p["text"] for p in kept((text, ["S1"]))[0]] == [text], text


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
    assert paragraphs[0]["text"] == "No other posts in the database say so; this database is short."


def test_an_answer_says_database_where_it_would_say_record():
    """John, 28 October: "shared database" instead of "shared record", in answers too."""
    paragraphs, _ = kept(("The record holds two views. Nothing in the record says why; the Record is short.", ["P1"]))
    assert paragraphs[0]["text"] == "The database holds two views. Nothing in the database says why; the database is short."


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
    assert empty.status == "empty" and empty.message == "The database does not say anything about this yet."
    partial_digest = ask.Digest(DIGEST.text, SOURCES, posts_in=2, posts_left_out=4)
    partial = ask.answer("Why?", [], partial_digest, SETTINGS,
                         transport=service(json.dumps(reply(("Ada wants a tax.", ["P1"]))), calls))
    assert partial.partial is True


def test_an_empty_record_is_never_sent(monkeypatch):
    monkeypatch.setattr(ask, "call_model", lambda *args, **kw: pytest.fail("the reading service was asked"))
    nothing = ask.Digest('{"asked_about":"the whole record","issues":[]}', {})
    only_evidence = ask.Digest("{}", {"E1": SOURCES["E1"]})
    for digest in (nothing, only_evidence):
        assert digest.empty
        result = ask.answer("Why?", [], digest, SETTINGS)
        assert result.status == "empty" and result.message == "The database does not say anything about this yet."
    assert not DIGEST.empty


def test_the_timeout_is_forty_seconds(monkeypatch):
    seen = {}
    monkeypatch.setattr(ask, "call_model", lambda messages, settings, **kw: seen.update(kw))
    ask.answer("Why?", [], DIGEST, SETTINGS)
    assert (seen["timeout"], seen["attempts"], seen["max_tokens"]) == (40, 1, 700)


def test_the_rules_have_no_dashes_where_a_reader_could_see_them():
    for line in (ask.EMPTY, ask.PARTIAL, ask.FAILED):
        assert "-" not in line and "\u2014" not in line and "\u2013" not in line


# John, 28 October: Ask must answer from the guiding documents too ("what does the UDHR say about privacy",
# "is a global carbon tax consistent with Earth Charter 7d"). They are cited as D1 to D3.
ARTICLE_12 = ("No one shall be subjected to arbitrary interference with his privacy, family, home or "
              "correspondence, nor to attacks upon his honour and reputation.")


def test_the_rules_name_the_three_documents_and_their_ids():
    rules = " ".join(ask.ANSWERING_RULES.split())
    assert "D1 the Statement of purpose, D2 the Universal Declaration of Human Rights, D3 the Earth Charter" in rules
    assert ask.SYSTEM_PROMPT.startswith("\n" + guiding_block() + "\n")


def test_a_paragraph_quoting_a_document_needs_no_post():
    paragraphs, counts = kept((f"Article 12 of the Declaration says: “{ARTICLE_12}”", ["D2"]))
    assert paragraphs == [{"text": f"Article 12 of the Declaration says: “{ARTICLE_12}”", "sources": ["D2"]}]
    assert counts == {"paragraphs_dropped": 0, "sources_kept": 1, "sources_dropped": 0}


def test_a_quote_cut_short_or_split_by_an_ellipsis_still_counts():
    text = ("Article 12 says \"No one shall be subjected to arbitrary interference with his privacy… "
            "nor to attacks upon his honour and reputation.\"")
    assert kept((text, ["D2"]))[0] == [{"text": text, "sources": ["D2"]}]


def test_a_quote_the_document_does_not_hold_is_dropped():
    paragraphs, counts = kept(("Article 12 says: “Everyone has the right to a private carbon budget.”", ["D2"]),
                              (f"The Charter says: “{ARTICLE_12}”", ["D3"]))
    assert paragraphs == [] and counts["paragraphs_dropped"] == 2


def test_only_the_three_documents_can_be_cited():
    paragraphs, counts = kept(("The Declaration speaks of privacy in Article 12.", ["D2", "D4", "D0"]))
    assert paragraphs == [{"text": "The Declaration speaks of privacy in Article 12.", "sources": ["D2"]}]
    assert counts["sources_dropped"] == 2


def test_a_document_and_the_record_can_be_cited_together():
    text = "Earth Charter 7d asks that full environmental and social costs be internalized; Ada wants a carbon tax."
    paragraphs, _ = kept((text, ["D3", "P1", "S1"]))
    shown, sources = ask.numbered(paragraphs, DIGEST)
    assert shown == [{"text": text, "refs": [1, 2, 3]}]
    assert [(s.id, s.kind, s.name, s.href) for s in sources][0] == (
        "D3", "document", "The Earth Charter", "/about#earth-charter")


def test_a_bare_document_id_in_the_text_reads_as_its_name():
    paragraphs, _ = kept(("D2 Article 12 protects privacy.", ["D2"]))
    assert paragraphs[0]["text"] == "Universal Declaration of Human Rights Article 12 protects privacy."


@pytest.mark.parametrize("question, names", [
    ("What does the UDHR say about privacy?", True),
    ("Is a global carbon tax consistent with Earth Charter 7d?", True),
    ("Does the lack of a carbon tax violate the Universal Declaration of Human Rights?", True),
    ("Which article of the Declaration covers asylum?", True),
    ("What does the statement of purpose say?", True),
    ("Which principle speaks to this?", True),
    ("Why do people oppose the veto?", False),
    ("What is the evidence for a carbon tax?", False)])
def test_a_question_that_names_a_guiding_document(question, names):
    assert ask.names_document(question) is names


def test_an_empty_record_still_asks_when_the_question_names_a_document():
    empty = ask.Digest('{"asked_about":"the whole record","issues":[]}', {}, issue_keys=[])
    calls = []
    content = json.dumps(reply((f"Article 12 says: “{ARTICLE_12}”", ["D2"])))
    result = ask.answer("What does the UDHR say about privacy?", [], empty, SETTINGS, transport=service(content, calls))
    assert len(calls) == 1 and result.status == "answered"
    assert [s.id for s in result.sources] == ["D2"]
    assert ask.answer("Why oppose the veto?", [], empty, SETTINGS, transport=service(content, calls)).status == "empty"
    assert len(calls) == 1


def test_a_document_is_cited_only_when_a_question_names_one():
    """The live run of 28 October: "Is a carbon tax a good idea?" got an Earth Charter paragraph nobody asked for."""
    calls = []
    content = json.dumps(reply(("Ada wants a tax.", ["P1"]), ("The Charter asks that costs be internalized.", ["D3"])))
    result = ask.answer("Is a carbon tax a good idea?", [], DIGEST, SETTINGS, transport=service(content, calls))
    assert [p["text"] for p in result.paragraphs] == ["Ada wants a tax."] and [s.id for s in result.sources] == ["P1"]
    result = ask.answer("And under 7d?", ["Is a carbon tax consistent with the Earth Charter?"], DIGEST, SETTINGS,
                        transport=service(content, calls))
    assert [s.id for s in result.sources] == ["P1", "D3"]
