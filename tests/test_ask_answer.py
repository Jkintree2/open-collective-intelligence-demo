"""Phase 3, ask the record: the answering call and the guard on its reply (ask.answer, ask.guard). No network."""

import json
import logging
from dataclasses import replace

import httpx
import pytest

from app import about_site, ask
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
NOTHING = ask.Digest('{"asked_about":"the whole record","issues":[]}', {}, issue_keys=[])  # a record that holds nothing


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


def test_a_paragraph_on_evidence_takes_the_posts_that_cited_it():
    """Case A4, 3 November: "Which evidence is most supported by other evidence?" was answered rightly in six runs of
    six, citing the three pieces and no post, so the guard dropped it and the page said the database holds nothing.
    Rule 3 asks for the post that cited each piece; the guard now adds it, from the digest."""
    sources = {**SOURCES, "E2": ask.Source("E2", "evidence", "IMF price floor", href="/issues/climate", issue="Climate"),
               "E3": ask.Source("E3", "evidence", "A page no post cited", href="/issues/climate", issue="Climate")}
    digest = ask.Digest(DIGEST.text, sources, posts_in=2, evidence_posts={"E1": ["P2"], "E2": ["P1", "P2"]})
    text = "Only the World Bank dashboard is supported by other evidence: the IMF price floor, read as agreeing."
    paragraphs, counts = ask.guard(reply((text, ["E1", "E2"]), ("A page no one cited says so.", ["E3"]),
                                         ("The dashboard is backed by 2 other pieces of evidence.", ["E1"]),
                                         ("Ada Okafor cites the dashboard.", ["E1", "P1"])), digest)
    assert paragraphs == [{"text": text, "sources": ["E1", "E2", "P2", "P1"]},
                          {"text": "The dashboard is backed by 2 other pieces of evidence.", "sources": ["E1"]},
                          {"text": "Ada Okafor cites the dashboard.", "sources": ["E1", "P1"]}]
    assert counts == {"paragraphs_dropped": 1, "sources_kept": 7, "sources_dropped": 0}


def test_a_number_word_counts_only_beside_what_it_counts():
    """The final review: "One solution is to ban cars." on an S id alone is a claim, not a count."""
    for text in ("One solution is to ban cars.", "No reason is given for it.", "None of this is settled."):
        assert kept((text, ["S1"]))[0] == [], text
    for text in ("No evidence here is supported or refuted by other evidence.", "Three people oppose it.",
                 "Two other pieces of evidence back it.", "Opposed by none, approved by two.",
                 "Approved by 4, opposed by 3, as of 17 October."):
        assert [p["text"] for p in kept((text, ["S1"]))[0]] == [text], text


def test_a_count_line_may_run_to_several_sentences_when_each_is_a_count():
    """The case run of 30 October: asked which solutions have the most approval, a short answer was the counts
    alone, 211 characters on S ids, 3 runs of 3, and the 200 character limit dropped the whole answer. Each
    sentence is held to the count line's test instead; one that is not a count makes it a claim again."""
    counts_only = ("A global carbon tax by referendum leads with 4 approvals against 3 opposed, as of 17 October. "
                   "Carbon border adjustment has 3 approvals and 1 opposed, and carbon fee and dividend has 1 "
                   "approval and no opposition.")
    assert [p["text"] for p in kept((counts_only, ["S1"]))[0]] == [counts_only]
    for text in ("Approved by 4, opposed by 3. It will end climate change.",
                 "Approved by 4. " + "y" * 200 + " by 3 people."):
        assert kept((text, ["S1"]))[0] == [], text


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


def test_an_answer_is_two_or_three_sentences_unless_the_question_asks_for_more():
    """John, 30 October: "more conversational if the answers were limited to two or three sentences instead of
    a list of all related entities in the database, unless an expanded answer is requested". The guard's five
    paragraphs and 1,200 characters stay as the ceiling of the longer answer."""
    rules = " ".join(ask.ANSWERING_RULES.split())
    assert ("Two or three sentences in all, under 400 characters not counting a quotation, the most important point "
            "first") in rules
    assert ('Only when the question asks for more, as in "tell me more", "in detail" or "list them all", write up '
            "to 5 short paragraphs") in rules
    assert "give the most held and say there are others" in rules  # rule 2: a short answer cannot hold each view
    # The case run of 30 October: the first wording still gave the evidence a paragraph of its own.
    assert "in a short answer, in a few words beside the point, never a sentence of its own" in rules
    assert "At most 5 short paragraphs" not in rules
    assert (ask.PARAGRAPHS_MAX, ask.ANSWER_CHARS) == (5, 1200)


# John, 28 October: Ask must answer from the guiding documents too ("what does the UDHR say about privacy",
# "is a global carbon tax consistent with Earth Charter 7d"). They are cited as D1 to D3.
ARTICLE_12 = ("No one shall be subjected to arbitrary interference with his privacy, family, home or "
              "correspondence, nor to attacks upon his honour and reputation.")


def test_the_rules_name_the_three_documents_and_their_ids():
    rules = " ".join(ask.ANSWERING_RULES.split())
    assert "D1 the Statement of purpose, D2 the Universal Declaration of Human Rights, D3 the Earth Charter" in rules
    assert ask.SYSTEM_PROMPT.startswith("\n" + guiding_block() + "\n")


ARTICLE_25 = ("Everyone has the right to a standard of living adequate for the health and well-being of himself and "
              "of his family, including food, clothing, housing and medical care and necessary social services")
ON_POSTS = ("Ada Okafor ties homelessness in St. Louis to the Declaration through a global referendum.", ["P1"])


def test_beside_posts_a_document_paragraph_does_not_add_that_no_post_speaks_to_it():
    """John, 3 November: an answer that cited three posts on homelessness then said "The database holds no post that
    sets homelessness beside this article." Rule 3 asks for that line only when no post speaks to the question."""
    paragraphs, counts = kept(ON_POSTS, (f'Article 25 says: "{ARTICLE_25}..." The database holds no post that sets '
                                         "homelessness in St. Louis beside this article.", ["D2"]))
    assert paragraphs == [{"text": ON_POSTS[0], "sources": ["P1"]},
                          {"text": f'Article 25 says: "{ARTICLE_25}..."', "sources": ["D2"]}]
    assert counts["paragraphs_dropped"] == 0
    paragraphs, _ = kept(ON_POSTS, (f"None of the posts sets it beside Article 25. It says: “{ARTICLE_25}.”",
                                    ["D2"]))
    assert paragraphs[1]["text"] == f"It says: “{ARTICLE_25}.”"
    # The case run of 3 November said it this way too.
    paragraphs, _ = kept(ON_POSTS, (f'Article 25 says "{ARTICLE_25}..." Nothing in the database sets a carbon tax '
                                    "beside this article, so no verdict is given.", ["D2"]))
    assert paragraphs[1]["text"] == f'Article 25 says "{ARTICLE_25}..."'
    # A paragraph that is only that line goes; a quotation is never cut, though it says "No one".
    paragraphs, counts = kept(ON_POSTS, ("No post here links homelessness to an article.", ["D2"]),
                              (f"Article 12 says: “{ARTICLE_12}”", ["D2"]))
    assert paragraphs[1:] == [{"text": f"Article 12 says: “{ARTICLE_12}”", "sources": ["D2"]}]
    assert counts["paragraphs_dropped"] == 1


def test_with_no_post_on_the_question_a_document_paragraph_still_says_so():
    text = f"Article 12 says: “{ARTICLE_12}” No post here speaks of privacy."
    assert kept((text, ["D2"]))[0] == [{"text": text, "sources": ["D2"]}]


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
    empty = NOTHING
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


# John, 3 November: answers to "How does homelessness relate to the principles of the UDHR?" quoted Article 25 in 9
# case runs of 9, but named the solution that names it in only 3.
A25_NAME = "Use money from global carbon tax to realize Article 25 of the UDHR"
QUOTE_25 = {"text": f'Article 25 says: "{ARTICLE_25}..."', "sources": ["D2"]}
ARTICLE_SOURCES = {**SOURCES,
                   "S2": ask.Source("S2", "solution", A25_NAME, href="/issues/climate", issue="Climate"),
                   "S3": ask.Source("S3", "solution", "Pay for Article 250 of the city code", href="/issues/climate",
                                    issue="Climate")}
ARTICLE_DIGEST = ask.Digest(json.dumps({"solutions": [
    {"id": "S1", "name": "Carbon tax", "approved_by": 4, "opposed_by": 3,
     "stances": [{"stance": "approve", "date": "2026-10-01", "posts": ["P1"]}]},
    {"id": "S2", "name": A25_NAME, "approved_by": 1, "opposed_by": 0, "proposed_in": ["P2"],
     "stances": [{"stance": "approve", "date": "2026-10-03", "posts": ["P2"]}]},
    {"id": "S3", "name": "Pay for Article 250 of the city code", "approved_by": 0, "opposed_by": 0}]}),
    ARTICLE_SOURCES, posts_in=2, issue_keys=["climate"])
A25_LINE = {"text": f'Also in the database: the solution "{A25_NAME}", approved by 1, opposed by 0.',
            "sources": ["S2", "P2"]}


def test_a_solution_naming_the_quoted_article_follows_the_quote():
    on_posts = {"text": ON_POSTS[0], "sources": ["P1"]}
    assert ask.with_article_solutions([on_posts, QUOTE_25], ARTICLE_DIGEST) == [on_posts, QUOTE_25, A25_LINE]
    assert ask.with_article_solutions([QUOTE_25, on_posts], ARTICLE_DIGEST) == [QUOTE_25, A25_LINE, on_posts]


@pytest.mark.parametrize("paragraphs", [
    [{"text": f"Article 12 says: “{ARTICLE_12}”", "sources": ["D2"]}],  # no solution names Article 12
    [{"text": f"Article 2 says: “{ARTICLE_25}”", "sources": ["D2"]}],  # 2 is not 25
    [{"text": "Ada ties homelessness to Article 25.", "sources": ["P1"]}],  # not a quote of the document
    [QUOTE_25, {"text": "One post would use a carbon tax for housing.", "sources": ["S2", "P2"]}],  # already named
    []])
def test_no_line_without_a_quoted_article_a_solution_names_and_the_answer_left_out(paragraphs):
    assert ask.with_article_solutions(paragraphs, ARTICLE_DIGEST) == paragraphs


def test_the_answer_gives_the_solution_naming_the_article_it_quotes():
    calls = []
    content = json.dumps(reply(ON_POSTS, (QUOTE_25["text"], ["D2"])))
    result = ask.answer("How does homelessness relate to the principles of the UDHR?", [], ARTICLE_DIGEST, SETTINGS,
                        transport=service(content, calls))
    assert result.paragraphs[2] == {"text": A25_LINE["text"], "refs": [3, 4]}
    assert [s.id for s in result.sources] == ["P1", "D2", "S2", "P2"]


# John, 9 November: "which language model is being used by the prototype?" got the empty line. A question about the
# site itself is answered from the About page's text above the three documents, given after the rules as D4.
ABOUT_ON = replace(SETTINGS, ask_enabled=True, about_enabled=True, llm_base_url="https://api.deepseek.com",
                   llm_model="deepseek-v4-flash")
JOHNS = "Which language model is being used by the prototype?"


@pytest.mark.parametrize("question", [JOHNS, "Where does this site run?", "Is the code open source?",
                                      "Who built this platform?", "What is sent to the model?",
                                      "Which model do you use?", "Where is the data stored?",
                                      "How are my questions used?", "What AI does the site use?"])
def test_names_site(question):
    assert ask.names_site(question)


@pytest.mark.parametrize("question", ["What can be done about homelessness in St. Louis?", "Tell me more", "Why?",
                                      "Who runs the city council?", "Who made the decision on rents?",
                                      "What do people say about AI in schools?", "Should cities be hosting the Olympics?",
                                      "Is a driver's license a right?", "What would render this solution useless?",
                                      "Who owns the site of the old steel plant?",
                                      "What do people say about artificial intelligence?"])
def test_does_not_name_site(question):
    assert not ask.names_site(question)


def test_the_about_page_follows_the_rules_as_d4():
    about = about_site.site_text(ABOUT_ON)
    prompt = ask.system_prompt(about)
    assert prompt.startswith(ask.SYSTEM_PROMPT) and prompt.endswith("\n\nD4, About this site:\n" + about)
    assert "Never cite D4 for a question about an issue, a solution or evidence." in " ".join(prompt.split())


def test_without_about_the_prompt_is_todays():
    assert ask.system_prompt(None) == ask.SYSTEM_PROMPT


def site_reply(text="The site uses DeepSeek, version deepseek-v4-flash.", sources=("D4",)):
    return json.dumps(reply((text, list(sources))))


def test_a_question_about_the_site_is_answered_from_d4_on_an_empty_record():
    calls = []
    result = ask.answer(JOHNS, [], NOTHING, ABOUT_ON, site_questions=True, transport=service(site_reply(), calls))
    assert len(calls) == 1
    assert calls[0]["messages"][0]["content"] == ask.system_prompt(about_site.site_text(ABOUT_ON))
    assert result.status == "answered" and result.sources == [ask.SITE]
    assert (ask.SITE.id, ask.SITE.kind, ask.SITE.name, ask.SITE.href) == ("D4", "about", "About this site", "/about")


def test_d4_is_not_citable_for_a_question_about_an_issue():
    calls = []
    result = ask.answer("What is proposed for the climate?", [], DIGEST, ABOUT_ON, site_questions=True, transport=service(site_reply(), calls))
    assert len(calls) == 1 and result.status == "empty"


def test_a_follow_up_keeps_the_about_page():
    calls = []
    result = ask.answer("Tell me more", [JOHNS], NOTHING, ABOUT_ON, site_questions=True, transport=service(site_reply(), calls))
    assert len(calls) == 1 and result.status == "answered"


def test_a_quote_said_to_be_from_d4_must_be_in_it():
    calls = []
    content = site_reply('The About page says "the site is run by a large team of engineers".')
    assert ask.answer(JOHNS, [], NOTHING, ABOUT_ON, site_questions=True, transport=service(content, calls)).status == "empty"
    content = site_reply('It is "a test of a conversational platform" for collective problem solving.')
    assert ask.answer(JOHNS, [], NOTHING, ABOUT_ON, site_questions=True, transport=service(content, calls)).status == "answered"


def test_without_about_a_site_question_on_an_empty_record_is_not_sent():
    calls = []
    result = ask.answer(JOHNS, [], NOTHING, SETTINGS, site_questions=True, transport=service(site_reply(), calls))
    assert calls == [] and result.status == "empty"


def test_the_case_runner_asks_with_the_about_page_on():
    """The cases (scripts/asks.py) are asked with the About page on, so S1 and S2 get D4."""
    from scripts import asks
    asked = asks.with_about(SETTINGS)
    assert asked.about_enabled and asked.ask_enabled and asked.llm_api_key == SETTINGS.llm_api_key


def test_a_follow_up_to_a_question_about_the_site_stays_on_the_site():
    """QA, 9 November: "Tell me more" after John's question summed up the whole database instead of the site."""
    rules = " ".join(ask.ABOUT_RULES.split())
    assert ('A follow-up with no words of its own, such as "Tell me more" or "Why?", after a question about the site '
            "asks for more about the site: answer it from D4 alone.") in rules



def test_an_about_page_that_will_not_draw_never_stops_ask(monkeypatch, caplog):
    """Review, 9 November: John edits templates on GitHub; a broken _about_site.html must not fail every question."""
    def broken(settings):
        raise RuntimeError("template error")
    monkeypatch.setattr(about_site, "site_text", broken)
    calls = []
    content = json.dumps(reply(("Ada wants a tax.", ["P1"]), ("The site uses DeepSeek.", ["D4"])))
    with caplog.at_level(logging.WARNING, logger="oci"):
        result = ask.answer(JOHNS, [], DIGEST, ABOUT_ON, site_questions=True, transport=service(content, calls))
    assert calls[0]["messages"][0]["content"] == ask.SYSTEM_PROMPT
    assert result.status == "answered" and [s.id for s in result.sources] == ["P1"]
    assert any('"event": "about_text_failed"' in r.message for r in caplog.records)



# the builder, 9 November: questions about the site are for the readers Home is on for (the preview, for now); every
# other reader's Ask is exactly as it was, D4 and the follow-up gate included.
def test_without_home_a_reader_asks_as_before():
    calls = []
    result = ask.answer(JOHNS, [], DIGEST, ABOUT_ON, transport=service(site_reply(), calls))
    assert calls[0]["messages"][0]["content"] == ask.SYSTEM_PROMPT and result.status == "empty"
    result = ask.answer(JOHNS, [], NOTHING, ABOUT_ON, transport=service(site_reply(), calls))
    assert len(calls) == 1 and result.status == "empty"


@pytest.mark.parametrize("site_questions, answerable", [(False, False), (True, True)])
def test_a_wordless_follow_up_on_an_empty_record_is_as_before_without_home(site_questions, answerable):
    earlier = ["What does the UDHR say about privacy?"]
    assert ask.answerable_without_record("Tell me more", earlier, site_questions) is answerable
    assert ask.answerable_without_record("What does the UDHR say about privacy?", [], site_questions)


# John, 11 November 2026 ("Asking"): two ways an answer the record could give came back as "nothing yet".

def test_a_point_about_a_solution_takes_the_posts_that_proposed_it():
    """As a point about evidence takes the posts that cited it (case A4), a point citing only a solution takes the
    posts behind it, so it is not dropped as resting on no post."""
    digest = replace(DIGEST, solution_posts={"S1": ["P1"]})
    paragraphs, _ = ask.guard(reply(("Ada proposed taxing carbon at the border.", ["S1"])), digest)
    assert paragraphs == [{"text": "Ada proposed taxing carbon at the border.", "sources": ["S1", "P1"]}]
    # A solution with no post in the digest still rests on nothing.
    paragraphs, counts = ask.guard(reply(("Someone proposed a tax.", ["S1"])), DIGEST)
    assert paragraphs == [] and counts["paragraphs_dropped"] == 1


@pytest.mark.parametrize("question", ["Is abortion a human right?", "Is housing a human right or not?"])
def test_human_right_names_the_declaration(question):
    assert ask.names_document(question)
    assert ask.document_query(question) == 'udhr "universal declaration"'


def test_the_second_call_of_a_widened_question_gets_the_time_it_is_given(monkeypatch):
    """John, 13 November 2026: a question an item's page could not answer is asked again of the whole database,
    in the time the page still waits."""
    seen = {}
    monkeypatch.setattr(ask, "call_model", lambda messages, settings, **kw: seen.update(kw))
    ask.answer("Why?", [], DIGEST, SETTINGS)
    assert seen["timeout"] == ask.TIMEOUT
    ask.answer("Why?", [], DIGEST, SETTINGS, timeout=17.5)
    assert seen["timeout"] == 17.5
