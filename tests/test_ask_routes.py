"""Phase 3, ask the record: /ask, /api/ask and the box on the issue page, behind ASK_ENABLED. No database,
no reading service: the digest and the answer are stubbed."""

from datetime import datetime, timezone

import pytest

from app import ask, routes_ask
from app.auth import DailyLimit, KeyedLimit, MinuteBucket

ISSUE = {"key": "veto", "name": "Security Council veto", "parent_key": None, "parent_name": None, "children": []}
DIGEST = ask.Digest("{}", {"P1": ask.Source("P1", "post", "Anonymous", "2026-10-30", "The veto blocks action.",
                                            "/issues/veto", "Security Council veto")},
                    posts_in=1, posts_left_out=2, issue_keys=["veto"])
ANSWERED = ask.Answer("answered", [{"text": "One writer says the veto <blocks> action.", "refs": [1]}],
                      list(DIGEST.sources.values()), partial=True)
SAME_SITE = {"sec-fetch-site": "same-origin"}


@pytest.fixture
def asking(member_app, switch, monkeypatch):
    graph = member_app.main.graph
    monkeypatch.setattr(graph, "issue_header", lambda key: dict(ISSUE) if key == "veto" else None)
    monkeypatch.setattr(graph, "issue_claimants", lambda key: {"claims": 1, "people": 1, "names": []})
    monkeypatch.setattr(graph, "issue_evidence", lambda key: [])
    monkeypatch.setattr(graph, "issue_solutions", lambda key, me=None, ranked=False: [])
    monkeypatch.setattr(graph, "issue_posts", lambda key, limit: [])
    monkeypatch.setattr(routes_ask, "person_limit", KeyedLimit(30, 86400))
    monkeypatch.setattr(routes_ask, "site_daily", DailyLimit(capacity=300))
    monkeypatch.setattr(routes_ask, "site_minute", MinuteBucket(capacity=1000, period=60.0))
    calls = []
    monkeypatch.setattr(ask, "issue_digest", lambda key, **kw: calls.append(("issue", key)) or DIGEST)
    monkeypatch.setattr(ask, "record_digest", lambda question, **kw: calls.append(("record", question)) or DIGEST)
    monkeypatch.setattr(ask, "answer", lambda question, earlier, digest, settings, **kw:
                        calls.append(("answer", question, earlier, kw["scope"])) or ANSWERED)
    member_app.calls = calls
    member_app.sign_in()
    switch(ask_enabled=True, llm_api_key="test-key")
    return member_app


def post(client, body):
    return client.post("/api/ask", json=body, headers=SAME_SITE)


def test_switched_off_there_is_no_ask_anywhere(asking, switch):
    switch(ask_enabled=False)
    assert asking.client.get("/ask").status_code == 404
    assert post(asking.client, {"question": "Why?"}).status_code == 404
    assert asking.client.post("/ask", data={"question": "Why?"}, headers=SAME_SITE).status_code == 404
    page = asking.client.get("/issues/veto").text
    assert "Ask about this issue" not in page and "ask.js" not in page
    assert asking.calls == []


def test_switched_off_a_stranger_gets_not_found_not_the_door(asking, switch):
    switch(ask_enabled=False)
    asking.client.cookies.clear()
    assert asking.client.get("/ask", follow_redirects=False).status_code == 404


def test_the_ask_page_and_the_issue_box(asking):
    page = asking.client.get("/ask").text
    assert "<h1 id=\"ask-title\">Ask the record</h1>" in page
    assert "Ask a question in plain words. The answer is built only from what people have posted here, and names " \
           "the posts it comes from." in page
    assert 'placeholder="For example: What do people say about the Security Council veto?"' in page
    assert "Answers sum up what is in the record, including views that differ." in page
    assert '<script src="/static/ask.js?v=' in page and "data-issue" not in page
    issue = asking.client.get("/issues/veto").text
    assert '<h2 id="ask-title">Ask about this issue</h2>' in issue and 'data-issue="veto"' in issue
    assert "Answers come only from the posts about this issue and its sub-issues." in issue
    assert 'placeholder="For example: Why do people oppose these solutions?"' in issue
    # Under the evidence and above the posts.
    assert issue.index("Evidence about this issue") < issue.index("Ask about this issue") < issue.index(
        "Posts about this issue")


def test_a_stranger_is_sent_to_the_door(asking):
    asking.client.cookies.clear()
    assert asking.client.get("/ask", follow_redirects=False).status_code == 303
    assert post(asking.client, {"question": "Why?"}).status_code == 401


def test_the_passphrase_opens_ask_too(asking, switch):
    switch(accounts_enabled=False)
    asking.client.post("/enter", data={"passphrase": "gate words", "next": "/"}, follow_redirects=False)
    assert asking.client.get("/ask").status_code == 200
    assert post(asking.client, {"question": "Why?"}).json()["status"] == "answered"


def test_an_answer_with_its_sources(asking):
    response = post(asking.client, {"question": "  Why is the veto   opposed? ", "earlier": ["Who?"], "issue": "veto"})
    body = response.json()
    assert response.status_code == 200 and body["status"] == "answered"
    assert body["paragraphs"] == [{"text": "One writer says the veto <blocks> action.", "refs": [1]}]
    assert body["sources"] == [{"id": "P1", "kind": "post", "name": "Anonymous", "date": "2026-10-30",
                                "text": "The veto blocks action.", "href": "/issues/veto",
                                "issue": "Security Council veto", "when": "30 October 2026"}]
    assert body["partial"] == "There are more posts on this than one answer can read, so this answer may leave " \
                              "some out."
    assert asking.calls == [("issue", "veto"), ("answer", "Why is the veto opposed?", ["Who?"], "issue")]


def test_the_whole_record_is_asked_without_an_issue(asking):
    post(asking.client, {"question": "What about the veto?"})
    assert asking.calls[0] == ("record", "What about the veto?") and asking.calls[1][3] == "record"


@pytest.mark.parametrize("question, message", [("", "Please write a question."), ("   ", "Please write a question."),
                                               ("x" * 501, "Please keep the question under 500 characters.")])
def test_a_question_that_cannot_go_ahead(asking, question, message):
    response = post(asking.client, {"question": question})
    assert response.status_code == 400 and response.json() == {"message": message}
    assert asking.calls == []


def test_an_unknown_issue_is_not_found(asking):
    assert post(asking.client, {"question": "Why?", "issue": "no such issue"}).status_code == 404


def test_without_the_reading_service_nothing_is_called_or_counted(asking, switch):
    switch(llm_api_key=None)
    for _ in range(35):
        body = post(asking.client, {"question": "Why?"}).json()
    assert body == {"message": "Asking needs the reading service, which is not set up."}
    assert asking.calls == [] and routes_ask.person_limit.uses == {}


def test_thirty_questions_a_person_a_day(asking):
    for _ in range(30):
        assert post(asking.client, {"question": "Why?"}).status_code == 200
    response = post(asking.client, {"question": "Why?"})
    assert response.status_code == 429
    assert response.json() == {"message": "You have asked 30 questions today. Please ask again tomorrow."}
    asking.sign_in(key="acct:ben", email="ben@example.org")
    assert post(asking.client, {"question": "Why?"}).status_code == 200


def test_three_hundred_for_the_site_and_the_person_is_not_charged(asking, monkeypatch):
    monkeypatch.setattr(routes_ask, "site_daily", DailyLimit(capacity=2))
    for _ in range(2):
        assert post(asking.client, {"question": "Why?"}).status_code == 200
    response = post(asking.client, {"question": "Why?"})
    assert response.status_code == 429
    assert response.json() == {"message": "The site has answered as many questions as it can today. "
                                          "Please ask again tomorrow."}
    assert len(routes_ask.person_limit.uses["acct:ada"]) == 2
    assert routes_ask.site_daily.capacity == 2 and DailyLimit().capacity == 300


def test_a_question_from_another_site_is_refused(asking):
    response = asking.client.post("/api/ask", json={"question": "Why?"},
                                  headers={"origin": "https://elsewhere.example"})
    assert response.status_code == 403 and asking.calls == []


def test_without_javascript_the_form_answers_on_the_ask_page(asking):
    page = asking.client.post("/ask", data={"question": "Why is the veto opposed?", "issue": "veto"},
                              headers=SAME_SITE).text
    assert '<h1 id="ask-title">Ask about this issue</h1>' in page
    assert '<a href="/issues/veto">Security Council veto</a>' in page
    assert "One writer says the veto &lt;blocks&gt; action." in page and "<blocks>" not in page
    assert "<span class=\"ask-refs\"> [1]</span>" in page
    assert "Anonymous, 30 October 2026: “The veto blocks action.” On <a href=\"/issues/veto\">" in page
    assert "There are more posts on this than one answer can read" in page
    short = asking.client.post("/ask", data={"question": ""}, headers=SAME_SITE)
    assert short.status_code == 400 and "Please write a question." in short.text


def test_the_page_copy_has_no_dashes_or_forbidden_words(asking):
    words = (routes_ask.NO_QUESTION, routes_ask.TOO_LONG, routes_ask.PERSON_LIMIT, routes_ask.SITE_LIMIT,
             routes_ask.NO_SERVICE, ask.EMPTY, ask.PARTIAL, ask.FAILED)
    page = asking.client.get("/ask").text + asking.client.get("/issues/veto").text
    for text in words + (page,):
        lowered = text.lower()
        for word in (" node", " edge", " graph", "cypher", " model", "extraction", " entity"):
            assert word not in lowered, word
    for text in words:
        assert "-" not in text and "–" not in text and "—" not in text
