"""Phase 3, ask the record: /ask, /api/ask and the box on the issue page, behind ASK_ENABLED. No database,
no reading service: the digest and the answer are stubbed."""

from datetime import datetime, timezone

import re

import pytest

from app import ask, graph_ask, graph_questions, routes_ask
from app.auth import DailyLimit, KeyedLimit, MinuteBucket

ISSUE = {"key": "veto", "name": "Security Council veto", "parent_key": None, "parent_name": None, "children": []}
DIGEST = ask.Digest("{}", {"P1": ask.Source("P1", "post", "Anonymous", "2026-10-30", "The veto blocks action.",
                                            "/issues/veto", "Security Council veto", "post-1")},
                    posts_in=1, posts_left_out=2, issue_keys=["veto"])
QUESTION_ID = "0f" * 16
ANSWERED = ask.Answer("answered", [{"text": "One writer says the veto <blocks> action.", "refs": [1]}],
                      list(DIGEST.sources.values()), partial=True)
SAME_SITE = {"sec-fetch-site": "same-origin"}
# As the module sets them, before a fixture swaps them for roomy ones.
DEFAULT_LIMITS = (routes_ask.site_minute.capacity, routes_ask.site_daily.capacity, routes_ask.person_limit.count)


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
    member_app.kept, member_app.answers, member_app.listed = [], [], []

    def keep(text, issue, now, answer):
        member_app.kept.append((text, issue))
        member_app.answers.append(answer)
        return QUESTION_ID
    monkeypatch.setattr(graph_questions, "keep", keep)
    monkeypatch.setattr(graph_questions, "recent", lambda issue=None, limit=10: list(member_app.listed))
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
    assert "<h1 id=\"ask-title\">Ask the database</h1>" in page
    assert "Ask a question in plain words. The answer is built only from what people have posted here and the three " \
           "guiding documents, and names where each part comes from." in page
    # John, 28 October: an empty box with the cursor in it, no example question.
    assert '<textarea name="question" rows="2" aria-labelledby="ask-title" autofocus>' in page
    assert "For example" not in page
    assert "Answers sum up what is in the database in two or three sentences, including views that differ;" in page
    assert '<script src="/static/ask.js?v=' in page and "data-issue" not in page
    issue = asking.client.get("/issues/veto").text
    assert '<h2 id="ask-title">Ask about this issue</h2>' in issue and 'data-issue="veto"' in issue
    assert "Answers come only from the posts about this issue and its sub-issues, and from the guiding documents when a question asks about them." in issue
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
    assert body == {"message": "Asking needs the language model, which is not set up."}
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
        lowered = text.lower().replace("language model", "")  # John's own words since 28 October (rule 5)
        for word in (" node", " edge", " graph", "cypher", " model", "extraction", " entity"):
            assert word not in lowered, word
    for text in words:
        assert "-" not in text and "–" not in text and "—" not in text


def test_without_javascript_the_last_three_questions_are_carried_never_the_answers(asking, monkeypatch):
    with_solution = ask.Answer("answered", [{"text": "Approved by 2, as of 30 October.", "refs": [1]}],
                               [ask.Source("S1", "solution", "Limit the veto", href="/issues/veto",
                                           issue="Security Council veto")])
    monkeypatch.setattr(ask, "answer", lambda question, earlier, digest, settings, **kw:
                        asking.calls.append(("answer", question, earlier)) or with_solution)
    page = asking.client.post("/ask", data={"question": "Four?", "earlier": ["One?", "Two?", "Three?"]},
                              headers=SAME_SITE).text
    assert asking.calls[-1] == ("answer", "Four?", ["One?", "Two?", "Three?"])
    hidden = [line.split('value="')[1].split('"')[0] for line in page.splitlines() if 'name="earlier"' in line
              for line in line.split("<input")[1:]]
    assert hidden == ["Two?", "Three?", "Four?"]
    assert "Approved by 2" in page and 'name="earlier" value="Approved' not in page
    assert "Solution: Limit the veto. On <a href=\"/issues/veto\">Security Council veto</a>" in page
    assert '<textarea name="question"' in page and "Four?</textarea>" not in page


def test_without_javascript_a_question_not_asked_is_not_carried(asking):
    page = asking.client.post("/ask", data={"question": "x" * 600, "earlier": ["One?"]}, headers=SAME_SITE).text
    assert 'name="earlier" value="One?"' in page and 'value="xxx' not in page
    assert ("x" * 600 + "</textarea>") in page  # kept in the box to shorten


def test_five_a_minute_for_the_site_and_the_person_is_not_charged(asking, monkeypatch):
    """The final review: 40 second calls on a tenth of a CPU. The default bucket holds five."""
    assert DEFAULT_LIMITS == (5, 300, 30)
    monkeypatch.setattr(routes_ask, "site_minute", MinuteBucket(capacity=1, period=60.0))
    assert post(asking.client, {"question": "Why?"}).status_code == 200
    response = post(asking.client, {"question": "Why?"})
    assert response.status_code == 429
    assert response.json() == {"message": "The question could not be answered just now. Please try again in a minute."}
    assert len(routes_ask.person_limit.uses["acct:ada"]) == 1


def test_an_empty_record_answers_the_empty_line_with_no_call_and_no_count(asking, monkeypatch):
    monkeypatch.setattr(ask, "issue_digest", lambda key, **kw: ask.Digest("{}", {}, issue_keys=[key]))
    body = post(asking.client, {"question": "Why?", "issue": "veto"}).json()
    assert body["status"] == "empty" and body["message"] == "The database does not say anything about this yet."
    assert [call for call in asking.calls if call[0] == "answer"] == [] and routes_ask.person_limit.uses == {}


def test_an_empty_record_still_answers_a_question_about_a_guiding_document(asking, monkeypatch):
    """John, 28 October: "What does the UDHR say about privacy?" found no post and got the empty line."""
    monkeypatch.setattr(ask, "record_digest", lambda question, **kw: ask.Digest("{}", {}, issue_keys=[]))
    body = post(asking.client, {"question": "What does the UDHR say about privacy?"}).json()
    assert body["status"] == "answered"
    assert asking.calls[-1][:2] == ("answer", "What does the UDHR say about privacy?")
    assert len(routes_ask.person_limit.uses["acct:ada"]) == 1


@pytest.mark.parametrize("about_on, href", [(True, "/about#udhr"), (False, None)])
def test_a_document_source_links_to_the_about_page_only_while_it_is_on(asking, monkeypatch, switch, about_on, href):
    document = ask.DOCUMENTS["D2"]
    monkeypatch.setattr(ask, "answer", lambda question, earlier, digest, settings, **kw:
                        ask.Answer("answered", [{"text": "Article 12 protects privacy.", "refs": [1]}], [document]))
    switch(about_enabled=about_on)
    body = post(asking.client, {"question": "What does the UDHR say about privacy?"}).json()
    assert body["sources"] == [{"id": "D2", "kind": "document", "name": "Universal Declaration of Human Rights",
                                "date": None, "text": None, "href": href, "issue": None, "when": None}]
    assert document.href == "/about#udhr"  # the shared source is never changed in place
    page = asking.client.post("/ask", data={"question": "What does the UDHR say about privacy?"}, headers=SAME_SITE).text
    line = re.search(r'<ol class="ask-sources">\s*<li>(.*?)</li>', page, flags=re.S).group(1)
    assert line == ("Guiding document: <a href=\"/about#udhr\">Universal Declaration of Human Rights</a>." if about_on
                    else "Guiding document: Universal Declaration of Human Rights.")


def test_a_use_can_be_given_back():
    limit = KeyedLimit(2, 60)
    assert limit.take("a", now=0) and limit.take("a", now=1) and not limit.take("a", now=2)
    limit.give_back("a")
    assert limit.take("a", now=3)
    limit.give_back("a")
    limit.give_back("a")
    limit.give_back("a")  # nothing left to give back: no error
    assert limit.uses == {}
    limit.give_back("never")


# John, 28 October: an answered question is kept, without who asked, and the latest are listed under the box.
def test_an_answered_question_is_kept_without_who_asked(asking):
    post(asking.client, {"question": "  Why   the veto? ", "issue": "veto"})
    post(asking.client, {"question": "Who opposes it?"})
    assert asking.kept == [("Why the veto?", "veto"), ("Who opposes it?", None)]


def test_a_question_not_answered_is_not_kept(asking, monkeypatch, switch):
    monkeypatch.setattr(ask, "answer", lambda *a, **kw: ask.Answer("failed"))
    post(asking.client, {"question": "Why?"})
    monkeypatch.setattr(ask, "answer", lambda *a, **kw: ask.Answer("empty"))
    post(asking.client, {"question": "Why?"})
    switch(llm_api_key="")
    post(asking.client, {"question": "Why?"})
    post(asking.client, {"question": ""})
    assert asking.kept == []


def test_an_answer_still_shows_when_the_question_cannot_be_kept(asking, monkeypatch, caplog):
    def broken(*args):
        raise RuntimeError("asleep")
    monkeypatch.setattr(graph_questions, "keep", broken)
    body = post(asking.client, {"question": "Why?"}).json()
    assert body["status"] == "answered" and body["question_id"] is None
    assert "question_not_kept" in caplog.text and "Why?" not in caplog.text


# John, 30 October: "Each item in the list of questions asked definitely needs to be a link to the answer."
def test_an_answered_question_is_kept_with_its_answer(asking):
    body = post(asking.client, {"question": "Why the veto?", "issue": "veto"}).json()
    assert body["question_id"] == QUESTION_ID
    assert asking.answers == [{
        "paragraphs": [{"text": "One writer says the veto <blocks> action.", "refs": [1]}],
        "sources": [{"id": "P1", "kind": "post", "name": "Anonymous", "date": "2026-10-30",
                     "text": "The veto blocks action.", "href": "/issues/veto", "issue": "Security Council veto",
                     "post_id": "post-1"}],
        "partial": ask.PARTIAL}]
    assert "post_id" not in body["sources"][0]  # the page never needs a post's id


ASKED_AT = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
KEPT_ANSWER = {
    "paragraphs": [{"text": "One writer says the veto <blocks> action.", "refs": [1]},
                   {"text": "Article 1 says so.", "refs": [2]}],
    "sources": [{"id": "P1", "kind": "post", "name": "Anonymous", "date": "2026-10-29",
                 "text": "The veto blocks action.", "href": "/issues/veto", "issue": "Security Council veto",
                 "post_id": "post-1"},
                {"id": "D2", "kind": "document", "name": "Universal Declaration of Human Rights", "date": None,
                 "text": None, "href": "/about#udhr", "issue": None, "post_id": None}],
    "partial": None}
POST_1 = {"id": "post-1", "text": "The veto blocks action.", "display_name": "Ada Okafor", "anonymous": True,
          "created_at": datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc), "seed": False,
          "edited_at": datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)}


@pytest.fixture
def kept_answer(asking, monkeypatch):
    asking.posts = {"post-1": dict(POST_1)}
    asking.question = {"text": "Why the <veto>?", "issue_key": "veto", "issue_name": "Security Council veto",
                       "answer": KEPT_ANSWER, "asked_at": ASKED_AT}
    asking.read = []
    monkeypatch.setattr(graph_questions, "one", lambda qid: asking.read.append(qid) or
                        (dict(asking.question) if qid == QUESTION_ID else None))
    monkeypatch.setattr(graph_ask, "posts_by_ids", lambda ids: [dict(asking.posts[i]) for i in ids if i in asking.posts])
    return asking


def test_a_listed_question_opens_the_answer_it_got(kept_answer):
    response = kept_answer.client.get(f"/ask/answers/{QUESTION_ID}")
    page = response.text
    assert response.status_code == 200
    assert '<h1 id="ask-title">An earlier answer</h1>' in page
    assert 'Asked about <a href="/issues/veto">Security Council veto</a>' in page
    assert '<p class="ask-question">Why the &lt;veto&gt;?</p>' in page
    assert "One writer says the veto &lt;blocks&gt; action.<span class=\"ask-refs\"> [1]</span>" in page
    assert "Anonymous, 29 October 2026: “The veto blocks action.” On <a href=\"/issues/veto\">" in page
    # About is off here, so the document is named without a link, as on the Ask page.
    assert "Guiding document: Universal Declaration of Human Rights." in page and 'href="/about#udhr"' not in page
    assert ("Answered on 30 October 2026. The database may have changed since, so ask again for an answer from "
            "what it holds now.") in page
    assert '<form class="ask-again-form" method="post" action="/ask">' in page
    assert '<input type="hidden" name="question" value="Why the &lt;veto&gt;?">' in page
    assert '<input type="hidden" name="issue" value="veto">' in page
    assert "post-1" not in page


@pytest.mark.parametrize("change", ["edited", "removed", "named"])
def test_an_answer_whose_post_changed_since_is_not_shown(kept_answer, change):
    """A kept answer may quote or name a post. Once that post is edited, deleted or shown under another name,
    the old answer could keep what its writer took back, so only the question and Ask again are shown."""
    if change == "edited":
        kept_answer.posts["post-1"]["edited_at"] = datetime(2026, 10, 30, 9, 30, tzinfo=timezone.utc)
    elif change == "removed":
        del kept_answer.posts["post-1"]
    else:
        kept_answer.posts["post-1"]["anonymous"] = False  # now shown as Ada Okafor, not Anonymous
    page = kept_answer.client.get(f"/ask/answers/{QUESTION_ID}").text
    assert ("A post this answer rested on has been edited or removed since, so the answer is no longer shown. Ask "
            "again for an answer from what the database holds now.") in page
    assert "blocks" not in page and "Ada Okafor" not in page and "Sources" not in page
    assert '<p class="ask-question">Why the &lt;veto&gt;?</p>' in page and ">Ask again</button>" in page


def test_an_answer_on_the_whole_database_has_no_issue_line(kept_answer):
    kept_answer.question.update(issue_key=None, issue_name=None)
    page = kept_answer.client.get(f"/ask/answers/{QUESTION_ID}").text
    assert "Asked about" not in page and 'name="issue"' not in page


@pytest.mark.parametrize("path", ["/ask/answers/" + "0" * 32, "/ask/answers/not-an-id", "/ask/answers/" + "0F" * 16])
def test_an_answer_that_is_not_kept_is_not_found(kept_answer, path):
    assert kept_answer.client.get(path).status_code == 404
    assert kept_answer.read in ([], ["0" * 32])  # a malformed id is never looked up


def test_a_question_kept_before_answers_were_has_no_answer_page(kept_answer):
    kept_answer.question["answer"] = None
    assert kept_answer.client.get(f"/ask/answers/{QUESTION_ID}").status_code == 404


def test_an_answer_page_needs_ask_and_the_door(kept_answer, switch):
    kept_answer.client.cookies.clear()
    assert kept_answer.client.get(f"/ask/answers/{QUESTION_ID}", follow_redirects=False).status_code == 303
    switch(ask_enabled=False)
    assert kept_answer.client.get(f"/ask/answers/{QUESTION_ID}", follow_redirects=False).status_code == 404
    assert kept_answer.read == []


def test_the_answer_page_copy_has_no_dashes_or_forbidden_words(kept_answer):
    page = kept_answer.client.get(f"/ask/answers/{QUESTION_ID}").text
    kept_answer.posts.clear()
    changed = kept_answer.client.get(f"/ask/answers/{QUESTION_ID}").text
    for text in (page, changed, routes_ask.ANSWERED_ON, routes_ask.ANSWER_CHANGED):
        lowered = text.lower().replace("language model", "")
        for word in (" node", " edge", " graph", "cypher", " model", "extraction", " entity"):
            assert word not in lowered, word
    for text in (routes_ask.ANSWERED_ON, routes_ask.ANSWER_CHANGED):
        assert "-" not in text and "–" not in text and "—" not in text


def test_the_ask_page_lists_the_latest_questions_and_their_issues(asking):
    assert 'data-ask-recent hidden' in asking.client.get("/ask").text  # none yet: the list waits, hidden
    asking.listed[:] = [{"text": "Why the <veto>?", "issue_key": "veto", "issue_name": "Security Council veto",
                         "id": QUESTION_ID, "answered": True},
                        {"text": "Who pays?", "issue_key": None, "issue_name": None, "id": None, "answered": False}]
    page = asking.client.get("/ask").text
    assert "<h3>Questions people are asking</h3>" in page and "data-ask-recent hidden" not in page
    # John, 30 October: "Each item in the list of questions asked definitely needs to be a link to the answer."
    assert f'<a class="ask-answered" href="/ask/answers/{QUESTION_ID}">Why the &lt;veto&gt;?</a> ' \
           '<span class="counts">On <a href="/issues/veto">Security Council veto</a></span>' in page
    # A question kept before answers were has none to open: a tap still puts it in the box.
    assert '<button type="button" class="ask-again">Who pays?</button></li>' in page
    assert ("Answers sum up what is in the database in two or three sentences, including views that differ; ask "
            "“Tell me more” for a longer one.") in page
    assert "A question that gets an answer is listed here for everyone with its answer, without your name." in page


def test_the_issue_box_lists_its_own_questions(asking, monkeypatch):
    seen = []
    monkeypatch.setattr(graph_questions, "recent", lambda issue=None, limit=10: seen.append((issue, limit)) or
                        [{"text": "Why the veto?", "issue_key": "veto", "issue_name": "Security Council veto",
                          "id": QUESTION_ID, "answered": True}])
    page = asking.client.get("/issues/veto").text
    assert seen == [("veto", 5)] and "<h3>Questions asked about this issue</h3>" in page
    # No "On" on its own issue.
    assert f'<a class="ask-answered" href="/ask/answers/{QUESTION_ID}">Why the veto?</a></li>' in page


def test_switched_off_no_question_is_read(asking, monkeypatch, switch):
    switch(ask_enabled=False)
    monkeypatch.setattr(graph_questions, "recent", lambda *a, **kw: pytest.fail("questions read with Ask off"))
    assert "data-ask-recent" not in asking.client.get("/issues/veto").text


def test_the_same_question_is_one_question_on_each_issue():
    key = graph_questions.question_key
    assert key("Why the veto?", "veto") == key("  why THE   veto ", "veto") == "veto|why the veto"
    assert key("Why the veto?", None) == "|why the veto" != key("Why the veto?", "climate")


# Call of 28 October: a menu under the issue's name, so everything on the page (Ask above all) is seen at once.
def menu(page):
    links = page.split('<nav class="issue-menu" aria-label="On this page">', 1)[1].split("</nav>", 1)[0]
    return re.findall(r'href="#([a-z-]+)">([^<]+)</a>', links)


def test_the_issue_page_menu_links_to_each_part(asking, switch, monkeypatch):
    page = asking.client.get("/issues/veto").text
    assert menu(page) == [("solutions", "Solutions (0)"), ("evidence", "Evidence (0)"), ("ask-title", "Ask"),
                          ("posts", "Posts")]
    assert all(f'id="{target}"' in page for target, _ in menu(page))
    children = [{"key": "a", "name": "A"}, {"key": "b", "name": "B"}]
    monkeypatch.setattr(asking.main.graph, "issue_header", lambda key: {**ISSUE, "children": children})
    page = asking.client.get("/issues/veto").text
    assert menu(page)[0] == ("sub-issues", "Sub-issues (2)") and 'id="sub-issues"' in page
    switch(ask_enabled=False)
    assert ("ask-title", "Ask") not in menu(asking.client.get("/issues/veto").text)
