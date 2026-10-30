"""GitHub issue 55 (John, 30 October 2026): a page for each solution and each piece of evidence, the Write page
opened from them, the links in from chips and answers, and Ask on those pages. Offline: the reads are stubbed."""

import json
import re
from datetime import datetime, timezone

import pytest

from app import ask, graph_item_pages, graph_questions, routes_ask
from app import extract as reading
from app.auth import DailyLimit, KeyedLimit, MinuteBucket
from app.extract import Candidates

SAME_SITE = {"sec-fetch-site": "same-origin"}
TAX = {"key": "carbon tax", "name": "Carbon tax", "proposers": 2, "proposed_by": ["Ada Tester", "Anonymous"],
       "approves": 4, "opposes": 3, "my_stance": None,
       "issues": [{"key": "climate", "name": "Climate", "parent_key": "world", "parent_name": "World"}],
       "evidence": [{"key": "who pays", "name": "Who pays study", "url": "https://example.org/who", "stance": "REFUTES"},
                    {"key": "letter", "name": "Open letter", "url": None, "stance": "SUPPORTS"}]}
STUDY = {"key": "who pays", "name": "Who pays study", "url": "https://example.org/who", "submitted_by": ["Anonymous"],
         "personal": None, "answers_key": None, "answers_name": None, "source_known": True, "source_type": "research",
         "source_primary": True, "source_published": "2019", "source_cites": None,
         "targets": [{"kind": "solution", "key": "carbon tax", "name": "Carbon tax", "stance": "REFUTES",
                      "home_key": "climate", "home_name": "Climate", "parent_key": "world", "parent_name": "World"},
                     {"kind": "issue", "key": "climate", "name": "Climate", "stance": "SUPPORTS", "home_key": None,
                      "home_name": None, "parent_key": "world", "parent_name": "World"}],
         "evidence": [{"key": "reply", "name": "A reply", "url": None, "stance": "REFUTES"}]}
POST = {"id": "p1", "text": "The tax hits poor households.", "display_name": None, "anonymous": True, "seed": False,
        "created_at": datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)}


@pytest.fixture
def pages(member_app, switch, monkeypatch):
    seen = {}

    def solution(key, me=None):
        seen["me"] = me
        return {**TAX, "issues": list(TAX["issues"]), "evidence": [dict(e) for e in TAX["evidence"]],
                "my_stance": "OPPOSE" if me else None} if key == "carbon tax" else None
    monkeypatch.setattr(graph_item_pages, "solution", solution)
    monkeypatch.setattr(graph_item_pages, "evidence", lambda key: json.loads(json.dumps(STUDY)) if key == "who pays" else None)
    monkeypatch.setattr(graph_item_pages, "solution_posts", lambda key, limit=60: [dict(POST)])
    monkeypatch.setattr(graph_item_pages, "evidence_posts", lambda key, limit=60: [dict(POST)])
    monkeypatch.setattr(graph_item_pages, "evidence_confidence", lambda key: [])
    monkeypatch.setattr("app.graph_evidence.issue_confidence", lambda key: [])
    member_app.seen = seen
    member_app.sign_in()
    return member_app


def test_a_solution_page_with_its_issue_proposers_stances_evidence_and_posts(pages):
    response = pages.client.get("/solutions/carbon%20tax")
    page = response.text
    assert response.status_code == 200 and pages.seen["me"] == "acct:ada"
    assert ('<p class="crumbs"><a href="/issues">Issues</a> › <a href="/issues/world">World</a> › '
            '<a href="/issues/climate">Climate</a> › Carbon tax</p>') in page
    assert "<h1>Carbon tax</h1>" in page
    assert '<a class="write-issue" href="/?solution=carbon%20tax">Write about this solution</a>' in page
    assert '<p class="claimed">Proposed by 2 people: Ada Tester, Anonymous</p>' in page
    # The issue page's buttons, posting back to this page (no issue in the form).
    assert '<form class="stance" method="post" action="/solutions/carbon%20tax/stance">' in page
    assert 'name="issue"' not in page.split('<form class="stance"')[1].split("</form>")[0]
    assert "You oppose this. Press Oppose again to withdraw." in page and "stances.js" in page
    assert '<a href="/issues/climate">Climate</a> <span class="by">part of World</span>' in page
    assert ('<p class="ev-label">Refuted by</p><ul class="evidence"><li><a href="/evidence/who%20pays">Who pays study</a> '
            '<a class="source-link" href="https://example.org/who" target="_blank" rel="noopener noreferrer">source</a>'
            '</li></ul>') in page
    assert '<li><a href="/evidence/letter">Open letter</a></li>' in page
    assert "The tax hits poor households." in page and "Posts about this solution" in page
    assert "Ask about this solution" not in page  # ASK_ENABLED unset


def test_an_evidence_page_with_its_source_what_it_speaks_to_and_its_posts(pages):
    page = pages.client.get("/evidence/who%20pays").text
    assert ('<p class="crumbs"><a href="/issues">Issues</a> › <a href="/issues/world">World</a> › '
            '<a href="/issues/climate">Climate</a> › <a href="/solutions/carbon%20tax">Carbon tax</a> › Who pays study</p>'
            ) in page
    assert '<a class="write-issue" href="/?evidence=who%20pays">Write about this evidence</a>' in page
    assert ('<p class="source-line">Source: <a href="https://example.org/who" target="_blank" '
            'rel="noopener noreferrer">https://example.org/who</a></p>') in page
    assert '<p class="claimed">Submitted by Anonymous</p>' in page
    assert 'Refutes solution of <a href="/solutions/carbon%20tax">Carbon tax</a> <span class="by">on Climate</span>' in page
    assert 'Supports issue of <a href="/issues/climate">Climate</a>' in page
    assert '<h2 id="evidence">Evidence about this evidence</h2>' in page and '<a href="/evidence/reply">A reply</a>' in page
    assert "A research paper" not in page  # source confidence only with EVIDENCE_CHECK_ENABLED
    assert "The tax hits poor households." in page


def test_with_the_evidence_check_the_evidence_page_says_its_source_confidence(pages, switch, monkeypatch):
    switch(evidence_check_enabled=True)
    rows = [{"target_kind": "solution", "target_key": "carbon tax", "evidence_key": key, "stance": "REFUTES",
             "check": check, "check_quote": None, "source_known": False} for key, check in
            (("who pays", "supports"), ("other", None))]
    monkeypatch.setattr(graph_item_pages, "evidence_confidence", lambda key: rows)
    page = pages.client.get("/evidence/who%20pays").text
    assert '<p class="counts">A research paper from 2019. More than five years old. Primary source.</p>' in page
    assert ('<span class="confidence">One other piece of evidence here says the same.</span>'
            '<span class="confidence differs">The page was read as agreeing with this.</span>') in page


def test_evidence_with_no_link_says_so(pages, monkeypatch):
    monkeypatch.setattr(graph_item_pages, "evidence", lambda key: {**json.loads(json.dumps(STUDY)), "url": None,
                                                                   "personal": True})
    assert '<p class="source-line">From personal experience.</p>' in pages.client.get("/evidence/who%20pays").text


def test_an_unknown_key_goes_to_the_issues_page_and_a_stranger_to_the_door(pages):
    for path in ("/solutions/nothing", "/evidence/nothing"):
        response = pages.client.get(path, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/issues"
    pages.client.cookies.clear()
    response = pages.client.get("/solutions/carbon%20tax", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].startswith("/sign-in?next=/solutions/")


def test_a_stance_taken_on_the_solution_page_comes_back_to_it(pages, monkeypatch):
    monkeypatch.setattr("app.graph_stances.set_stance", lambda *args: None)
    response = pages.client.post("/solutions/carbon%20tax/stance", data={"choice": "approve"}, headers=SAME_SITE,
                                 follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/solutions/carbon%20tax?not_saved=carbon%20tax#solution-carbon-tax"
    page = pages.client.get("/solutions/carbon%20tax?not_saved=carbon%20tax").text
    assert "Your position was not saved. Please try again.</p>" in page


def test_chips_open_the_solution_and_evidence_pages(pages, monkeypatch):
    rows = [{"post_id": "p1", "from_label": "Person", "from_key": "acct:ada", "from_name": "Ada", "rel": "PROPOSE",
             "to_label": "Solution", "to_key": "carbon tax", "to_name": "Carbon tax", "anonymous": False,
             "home_key": "climate"},
            {"post_id": "p1", "from_label": "Evidence", "from_key": "who pays", "from_name": "Who pays study",
             "rel": "REFUTES", "to_label": "Solution", "to_key": "carbon tax", "to_name": "Carbon tax",
             "anonymous": None, "home_key": "climate"},
            {"post_id": "p1", "from_label": "Person", "from_key": "acct:ada", "from_name": "Ada", "rel": "CLAIM",
             "to_label": "Issue", "to_key": "climate", "to_name": "Climate", "anonymous": False, "home_key": None}]
    monkeypatch.setattr(pages.main.graph, "post_structure", lambda ids: {"p1": rows})
    chips = pages.main._decorate_posts([dict(POST)])[0]["chips"]
    assert [(chip["label"], chip["href"]) for chip in chips] == [
        ("Solution", "/solutions/carbon%20tax"), ("Evidence", "/evidence/who%20pays"), ("Issue", "/issues/climate")]


def test_the_write_page_from_a_solution_shows_it_with_the_three_positions(pages):
    page = pages.client.get("/?solution=carbon%20tax").text
    assert '<section class="about-issue" id="about-issue" data-issue="Climate" data-issue-key="climate">' in page
    assert "<h2>Already in the database for Carbon tax</h2>" in page
    assert '<p class="counts">Proposed for Climate</p>' in page
    assert 'value="approve" data-solution="Carbon tax"' in page and "I oppose this" in page
    assert "<li>Who pays study (refutes)</li>" in page
    assert '<a href="/solutions/carbon%20tax">Open the full page for this solution</a>' in page
    assert "about_issue.js" in page


def test_the_write_page_from_evidence_starts_from_its_first_issue(pages):
    page = pages.client.get("/?evidence=who%20pays").text
    assert '<section class="about-issue" id="about-issue" data-issue="Climate" data-issue-key="climate">' in page
    assert "<h2>Already in the database for Who pays study</h2>" in page
    assert "<li>Refutes solution of Carbon tax</li><li>Supports issue of Climate</li>" in page
    assert '<a href="/evidence/who%20pays">Open the full page for this evidence</a>' in page


def test_the_write_page_for_something_not_in_the_record_is_the_plain_write_page(pages):
    for path in ("/?solution=nothing", "/?evidence=nothing"):
        page = pages.client.get(path).text
        assert 'id="about-issue"' not in page and 'id="compose"' in page


def test_reading_from_a_solution_or_evidence_page_passes_it_on(pages, switch, monkeypatch):
    switch(llm_api_key="offline test key")
    seen, made = [], []
    monkeypatch.setattr(pages.main.graph, "candidates", lambda: made.append(
        Candidates(issues={"climate": {"name": "Climate", "parent_key": None}})) or made[-1])
    monkeypatch.setattr(pages.main.reading, "extract", lambda text, name, cands, settings, **kw:
                        seen.append((kw["writing_about"], dict(cands.solutions), dict(cands.evidence))) or None)
    pages.client.post("/api/extract", json={"text": "I support this.", "solution": "carbon tax"}, headers=SAME_SITE)
    pages.client.post("/api/extract", json={"text": "This is old.", "evidence": "who pays"}, headers=SAME_SITE)
    pages.client.post("/api/extract", json={"text": "Hello", "issue": "climate", "solution": "carbon tax"},
                      headers=SAME_SITE)
    # One the candidates did not hold (older than the newest 200) is added, so the reading can name it.
    assert seen == [(("solution", "carbon tax"), {"carbon tax": "Carbon tax"}, {}),
                    (("evidence", "who pays"), {}, {"who pays": "Who pays study"}),
                    ("climate", {}, {})]
    assert made[0].solution_issues == {"carbon tax": ["Climate"]}


def test_the_reading_is_told_about_a_solution_or_evidence_as_data():
    candidates = Candidates(issues={"climate": {"name": "Climate", "parent_key": None}},
                            solutions={"carbon tax": "Carbon tax"}, solution_issues={"carbon tax": ["Climate"]},
                            evidence={"who pays": "Who pays study"})

    def about(value):
        return json.loads(reading.build_messages("Text", "Tester", candidates, writing_about=value)[1]["content"])[
            "writing_about"]
    assert about(("solution", "carbon tax")) == {"solution": "Carbon tax", "for_issues": ["Climate"]}
    assert about(("evidence", "who pays")) == {"evidence": "Who pays study"}
    assert about(("solution", "nowhere")) is None and about(("evidence", "nowhere")) is None
    assert about("climate") == {"name": "Climate", "parent": None}


# Ask on the new pages, with ASK_ENABLED.

ANSWER = ask.Answer("answered", [{"text": "Three people oppose it.", "refs": [1, 2]}],
                    [ask.Source("S1", "solution", "Carbon tax", href="/issues/climate", issue="Climate",
                                page="/solutions/carbon%20tax"),
                     ask.Source("P1", "post", "Anonymous", "2026-10-29", "The tax hits", "/issues/climate", "Climate",
                                "p1")])


@pytest.fixture
def asking(pages, switch, monkeypatch):
    monkeypatch.setattr(routes_ask, "person_limit", KeyedLimit(30, 86400))
    monkeypatch.setattr(routes_ask, "site_daily", DailyLimit(capacity=300))
    monkeypatch.setattr(routes_ask, "site_minute", MinuteBucket(capacity=1000, period=60.0))
    calls, kept, listed = [], [], []
    digest = ask.Digest("{}", {s.id: s for s in ANSWER.sources})
    monkeypatch.setattr(ask, "solution_digest", lambda key, **kw: calls.append(("solution", key)) or digest)
    monkeypatch.setattr(ask, "evidence_digest", lambda key, **kw: calls.append(("evidence", key)) or digest)
    monkeypatch.setattr(ask, "answer", lambda question, earlier, digest, settings, **kw:
                        calls.append(("answer", kw["scope"])) or ANSWER)
    monkeypatch.setattr(graph_questions, "keep", lambda text, issue, now, answer, **on:
                        kept.append((text, issue, on, answer)) or "0f" * 16)
    monkeypatch.setattr(graph_questions, "recent", lambda issue=None, limit=10, **on: listed.append((issue, limit, on))
                        or [{"text": "Who pays?", "issue_key": None, "issue_name": None, "id": "0f" * 16,
                             "answered": True, "solution_key": "carbon tax", "solution_name": "Carbon tax",
                             "evidence_key": None, "evidence_name": None}])
    switch(ask_enabled=True, llm_api_key="test-key")
    pages.calls, pages.kept, pages.listed = calls, kept, listed
    return pages


def test_the_ask_box_on_a_solution_page_asks_about_that_solution(asking):
    page = asking.client.get("/solutions/carbon%20tax").text
    assert '<section class="ask" data-ask data-solution="carbon tax">' in page
    assert '<h2 id="ask-title">Ask about this solution</h2>' in page
    assert '<input type="hidden" name="solution" value="carbon tax">' in page
    assert "Answers come only from the posts about this solution, and from the guiding documents" in page
    assert "<h3>Questions asked about this solution</h3>" in page and "On <a" not in page
    assert asking.listed == [(None, graph_questions.RECENT_ON_ISSUE, {"solution_key": "carbon tax"})]
    body = asking.client.post("/api/ask", json={"question": "Who opposes it?", "solution": "carbon tax"},
                              headers=SAME_SITE).json()
    assert asking.calls == [("solution", "carbon tax"), ("answer", "solution")]
    assert body["solution"] == "Carbon tax" and body["issue"] is None
    assert body["sources"][0]["page"] == "/solutions/carbon%20tax" and "page" not in body["sources"][1]
    text, issue, on, answer = asking.kept[0]
    assert (text, issue, on) == ("Who opposes it?", None, {"solution_key": "carbon tax"})
    assert answer["sources"][0]["page"] == "/solutions/carbon%20tax" and "page" not in answer["sources"][1]


def test_the_ask_box_on_an_evidence_page_and_without_javascript(asking):
    page = asking.client.get("/evidence/who%20pays").text
    assert '<section class="ask" data-ask data-evidence="who pays">' in page
    assert '<h2 id="ask-title">Ask about this evidence</h2>' in page
    answered = asking.client.post("/ask", data={"question": "Is it reliable?", "evidence": "who pays"},
                                  headers=SAME_SITE).text
    assert asking.calls[0] == ("evidence", "who pays")
    assert ('<p class="crumbs"><a href="/issues">Issues</a> › <a href="/evidence/who%20pays">Who pays study</a></p>'
            in answered and '<h1 id="ask-title">Ask about this evidence</h1>' in answered)
    line = re.search(r'<ol class="ask-sources">\s*<li>(.*?)</li>', answered, flags=re.S).group(1)
    assert line == 'Solution: <a href="/solutions/carbon%20tax">Carbon tax</a>. On <a href="/issues/climate">Climate</a>'


def test_asking_about_something_not_in_the_record_is_not_found(asking):
    for body in ({"question": "Why?", "solution": "nothing"}, {"question": "Why?", "evidence": "nothing"}):
        assert asking.client.post("/api/ask", json=body, headers=SAME_SITE).status_code == 404
    assert asking.calls == []


def test_on_the_ask_page_a_question_asked_on_a_solution_says_which(asking):
    page = asking.client.get("/ask").text
    assert 'Who pays?</a> <span class="counts">On <a href="/solutions/carbon%20tax">Carbon tax</a></span>' in page


def test_a_kept_answer_asked_on_a_solution_links_back_to_it(asking, monkeypatch):
    kept = {"text": "Who pays?", "issue_key": None, "issue_name": None, "solution_key": "carbon tax",
            "solution_name": "Carbon tax", "evidence_key": None, "evidence_name": None,
            "asked_at": datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc),
            "answer": {"paragraphs": [{"text": "Three oppose it.", "refs": [1]}], "partial": None,
                       "sources": [{"id": "S1", "kind": "solution", "name": "Carbon tax", "date": None, "text": None,
                                    "href": "/issues/climate", "issue": "Climate", "post_id": None,
                                    "page": "/solutions/carbon%20tax"}]}}
    monkeypatch.setattr(graph_questions, "one", lambda qid: kept)
    page = asking.client.get("/ask/answers/" + "0f" * 16).text
    assert '<p class="ask-lead">Asked about <a href="/solutions/carbon%20tax">Carbon tax</a></p>' in page
    assert '<input type="hidden" name="solution" value="carbon tax">' in page
    assert 'Solution: <a href="/solutions/carbon%20tax">Carbon tax</a>.' in page
