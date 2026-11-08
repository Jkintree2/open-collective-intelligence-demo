"""v0.3, John's email of 7 November: Home's list is one "Recent posts" list, statements and questions from everyone
mixed, newest first, each question a link to its answer and each statement as it shows today; "My statements" becomes
"My posts", the member's own statements and questions mixed the same way. A member for whom Home is on is linked to
the questions they ask, so their own lists hold them on every device. No database."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from app import graph_questions
from test_home_switch import live_like  # noqa: F401
from test_phase3_switches import ALL_ON, POST, draw, pages  # noqa: F401

QID = "ab" * 16
AT = POST["created_at"]  # 1 October 2026, 12:00 UTC, "The veto blocks action." by Bob


def question(text, minutes, qid=QID, **on):
    row = {"text": text, "issue_key": None, "issue_name": None, "id": qid, "answered": qid is not None,
           "solution_key": None, "solution_name": None, "evidence_key": None, "evidence_name": None,
           "asked_at": AT + timedelta(minutes=minutes)}
    row.update(on)
    return row


@pytest.fixture
def homepage(live_like, switch):
    live_like.sign_in()
    switch(**ALL_ON, home_enabled="on")
    return live_like


def feed(page):
    return page[page.index('<section class="feed" id="feed">'):]


# Home: one mixed list.
def test_recent_posts_mix_statements_and_questions_newest_first(homepage, monkeypatch):
    rows = [question("Who pays for the carbon tax?", 60, issue_key="climate", issue_name="Climate"),
            question("Is the veto fair?", -60, qid="cd" * 16)]
    monkeypatch.setattr(graph_questions, "recent", lambda issue, limit, **on: rows)
    page = draw(homepage.client, "/")
    listed = feed(page)
    assert listed.count("<h2>Recent posts</h2>") == 1
    assert listed.index("Who pays for the carbon tax?") < listed.index("The veto blocks action.") \
        < listed.index("Is the veto fair?")
    assert f'<p class="statement"><a class="ask-answered" href="/ask/answers/{QID}">Who pays for the carbon tax?</a></p>' \
        in listed
    assert '<p class="counts">On <a href="/issues/climate">Climate</a></p>' in listed
    assert '<p class="byline">Question · <time datetime="2026-10-01T13:00:00+00:00"' in listed
    # The statement shows exactly as it does today, its byline and all.
    assert '<p class="byline">Bob · <time datetime="2026-10-01T12:00:00+00:00"' in listed
    assert "Questions people are asking" not in page


def test_a_question_asked_on_a_solution_or_evidence_names_it(homepage, monkeypatch):
    rows = [question("Does it work?", 5, solution_key="tax", solution_name="Carbon tax"),
            question("Is it true?", 4, qid="cd" * 16, evidence_key="ipcc", evidence_name="IPCC report")]
    monkeypatch.setattr(graph_questions, "recent", lambda issue, limit, **on: rows)
    listed = feed(draw(homepage.client, "/"))
    assert '<p class="counts">On <a href="/solutions/tax">Carbon tax</a></p>' in listed
    assert '<p class="counts">On <a href="/evidence/ipcc">IPCC report</a></p>' in listed


def test_a_question_kept_without_an_answer_link_goes_back_in_the_box(homepage, monkeypatch):
    monkeypatch.setattr(graph_questions, "recent", lambda issue, limit, **on: [question("Who pays?", 5, qid=None)])
    listed = feed(draw(homepage.client, "/"))
    assert '<p class="statement"><button type="button" class="home-again">Who pays?</button></p>' in listed


def test_the_mixed_list_holds_as_many_as_the_feed(homepage, monkeypatch):
    monkeypatch.setattr(homepage.main, "FEED_LIMIT", 3)
    monkeypatch.setattr(homepage.main.graph, "list_posts", lambda limit: [
        {**POST, "id": f"p{n}", "text": f"Statement {n}.", "created_at": AT - timedelta(minutes=n)}
        for n in range(limit)])
    asked = []
    monkeypatch.setattr(graph_questions, "recent", lambda issue, limit, **on: asked.append(limit) or [
        question(f"Question {n}?", 30 - n, qid=f"{n:032x}") for n in range(limit)])
    listed = feed(draw(homepage.client, "/"))
    assert asked == [3]
    assert re.findall(r"(Question \d\?|Statement \d\.)</", listed) == ["Question 0?", "Question 1?", "Question 2?"]


def test_the_feed_route_gives_a_home_reader_the_mix(homepage, monkeypatch):
    """card.js reloads #feed from /feed after a post; on Home it must stay the mixed list."""
    monkeypatch.setattr(graph_questions, "recent", lambda issue, limit, **on: [question("Who pays?", 5)])
    page = homepage.client.get("/feed").text
    assert page.index("Who pays?") < page.index("The veto blocks action.")


def test_without_home_the_feed_is_statements_only(homepage, switch, monkeypatch):
    monkeypatch.setattr(graph_questions, "recent", lambda *a, **kw: pytest.fail("no questions without Home"))
    for fields in ({"home_enabled": "off"}, {"home_enabled": "preview", "home_preview": ("bob@example.org",)},
                   {"home_enabled": "on", "ask_enabled": False}):
        switch(**fields)
        assert "The veto blocks action." in homepage.client.get("/feed").text
        assert "The veto blocks action." in draw(homepage.client, "/")


# Home: the member's own five, from the record on every device.
def own(number, minutes):
    return {"id": f"mine-{number}", "text": f"My statement number {number}.", "display_name": "Ada Tester",
            "anonymous": False, "seed": False,
            "created_at": datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes)}


def mine_question(text, minutes, qid):
    return {**question(text, 0, qid=qid), "asked_at": datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
            + timedelta(minutes=minutes)}


def mine_list(page):
    found = re.search(r'<ul id="home-mine">(.*?)</ul>', page, re.S).group(1)
    return re.findall(r'<li><a (?:class="ask-answered" )?href="([^"]+)">([^<]*)</a> <span class="counts">[^<]*</span></li>',
                      found)


def test_my_list_joins_my_questions_by_time(homepage):
    homepage.own_posts[:] = [own(1, -1), own(2, -3), own(3, -5)]
    homepage.own_questions[:] = [mine_question("Who pays?", 10, "01" * 16), mine_question("Is it fair?", -2, "02" * 16),
                                 mine_question("Why now?", -4, "03" * 16)]
    page = draw(homepage.client, "/")
    assert "<h2>My most recent statements and questions</h2>" in page
    assert mine_list(page) == [
        (f"/ask/answers/{'01' * 16}", "Who pays?"),
        ("/my-posts", "My statement number 1."),
        (f"/ask/answers/{'02' * 16}", "Is it fair?"),
        ("/my-posts", "My statement number 2."),
        (f"/ask/answers/{'03' * 16}", "Why now?")]
    assert '<section class="home-mine" id="home-mine-section">' in page


def test_with_only_a_question_the_list_shows(homepage):
    homepage.own_posts.clear()
    homepage.own_questions[:] = [mine_question("Who pays?", 0, QID)]
    page = draw(homepage.client, "/")
    assert '<section class="home-mine" id="home-mine-section">' in page and len(mine_list(page)) == 1


def test_with_ask_off_my_list_is_statements_only(homepage, switch, monkeypatch):
    monkeypatch.setattr(graph_questions, "mine", lambda *a, **kw: pytest.fail("no questions with Ask off"))
    switch(ask_enabled=False)
    homepage.own_posts[:] = [own(1, -1)]
    page = draw(homepage.client, "/")
    assert [href for href, _ in mine_list(page)] == ["/my-posts"]


def test_the_page_no_longer_names_the_member_for_the_device(homepage):
    for path in ("/", "/issues", "/ask", "/my-posts"):
        assert re.search(r"<body[^>]*>", draw(homepage.client, path)).group(0) == "<body>", path


# My posts.
NOW = datetime.now(timezone.utc)


def statements(n):
    return [{"id": f"p{i}", "text": f"Statement {i}", "display_name": "Ada Tester", "anonymous": False,
             "created_at": NOW - timedelta(minutes=2 * i), "seed": False} for i in range(n)]


def asked(n):
    return [{**question(f"Question {i}?", 0, qid=f"{i:032x}"), "asked_at": NOW - timedelta(minutes=2 * i + 1)}
            for i in range(n)]


def nav(page):
    return re.search(r"<nav>(.*?)</nav>", page, re.S).group(1)


def test_menu_says_my_posts_with_home_on(homepage):
    for path in ("/", "/issues", "/my-posts", "/my-statements"):
        menu = nav(draw(homepage.client, path))
        assert '<a href="/my-posts">My posts</a>' in menu and "My statements" not in menu, path


def test_my_posts_mixes_my_statements_and_questions_newest_first(homepage):
    homepage.own_posts[:] = statements(2)
    homepage.own_questions[:] = asked(2)
    page = draw(homepage.client, "/my-posts")
    assert "<title>My posts · " in page and "<h1>My posts</h1>" in page
    order = [page.index(text) for text in ("Statement 0<", "Question 0?", "Statement 1<", "Question 1?")]
    assert order == sorted(order)
    assert f'<a class="ask-answered" href="/ask/answers/{0:032x}">Question 0?</a>' in page
    assert 'href="/posts/p0/edit"' in page  # a statement keeps its Edit and Delete
    assert draw(homepage.client, "/my-statements") == page


def test_my_posts_fifty_at_a_time_counting_questions(homepage):
    homepage.own_posts[:] = statements(40)
    homepage.own_questions[:] = asked(40)
    page = draw(homepage.client, "/my-posts")
    assert "Question 24?" in page and "Statement 25<" not in page and "Question 25?" not in page
    assert 'href="/my-posts?shown=100">Show more</a>' in page
    page = draw(homepage.client, "/my-posts?shown=100")
    assert "Statement 39<" in page and "Question 39?" in page and "Show more" not in page


def test_my_posts_with_nothing_yet(homepage):
    homepage.own_posts.clear()
    assert "You have not posted anything yet." in draw(homepage.client, "/my-posts")


def test_without_home_my_statements_is_as_it_was(homepage, switch, monkeypatch):
    monkeypatch.setattr(graph_questions, "mine", lambda *a, **kw: pytest.fail("no questions without Home"))
    homepage.own_posts[:] = statements(1)
    for fields in ({"home_enabled": "off"}, {"home_enabled": "preview", "home_preview": ("bob@example.org",)}):
        switch(**fields)
        page = draw(homepage.client, "/my-statements")
        assert "<h1>My statements</h1>" in page and '<a href="/my-statements">My statements</a>' in nav(page)


def test_ask_off_my_posts_lists_statements_only(homepage, switch, monkeypatch):
    monkeypatch.setattr(graph_questions, "mine", lambda *a, **kw: pytest.fail("no questions with Ask off"))
    switch(ask_enabled=False)
    homepage.own_posts[:] = statements(1)
    assert "Statement 0<" in draw(homepage.client, "/my-posts")


def test_a_copy_carries_who_asked():
    from app.backup import DIRECTIONS
    assert DIRECTIONS["ASKED"] == ("Person", {"Question"})


def test_my_posts_address_is_not_found_without_home(homepage, switch):
    """Review of 04d36d4: /my-posts exists only while Home is on for the reader; /my-statements always."""
    for fields in ({"home_enabled": "off"}, {"home_enabled": "preview", "home_preview": ("bob@example.org",)}):
        switch(**fields)
        assert homepage.client.get("/my-posts").status_code == 404
        assert homepage.client.get("/my-statements").status_code == 200


# The list under the button, served alone so app.js can draw it again after a post or an answer (review, 8 November).
def test_home_mine_serves_the_list_alone(homepage):
    homepage.own_posts[:] = [own(1, -1)]
    homepage.own_questions[:] = [mine_question("Who pays?", 10, QID)]
    response = homepage.client.get("/home/mine")
    assert response.status_code == 200 and "no-store" in response.headers.get("cache-control", "")
    assert response.text.startswith('<section class="home-mine" id="home-mine-section">')
    assert mine_list(response.text) == [(f"/ask/answers/{QID}", "Who pays?"), ("/my-posts", "My statement number 1.")]
    assert "<nav>" not in response.text and "<html" not in response.text


def test_home_mine_is_not_found_without_home(homepage, switch):
    for fields in ({"home_enabled": "off"}, {"home_enabled": "preview", "home_preview": ("bob@example.org",)}):
        switch(**fields)
        assert homepage.client.get("/home/mine").status_code == 404
    homepage.client.cookies.clear()
    switch(home_enabled="on")
    assert homepage.client.get("/home/mine", follow_redirects=False).status_code in (303, 401)
