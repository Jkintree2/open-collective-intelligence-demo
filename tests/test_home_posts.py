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


def mine_question(text, minutes, qid):
    return {**question(text, 0, qid=qid), "asked_at": datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
            + timedelta(minutes=minutes)}


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


# John, 9 November: the list under the button is gone, and so is the address that drew it again.
def test_home_mine_is_gone(homepage):
    assert homepage.client.get("/home/mine").status_code == 404


def test_recent_posts_and_my_posts_leave_out_follow_ups(homepage, monkeypatch):
    """QA of v0.3, 8 November: a question with no words of its own ("Tell me more") kept before means nothing on a list."""
    rows = [question("Tell me more", 30, qid="cd" * 16), question("Who pays for the carbon tax?", 20)]
    monkeypatch.setattr(graph_questions, "recent", lambda issue, limit, **on: rows)
    homepage.own_posts.clear()
    homepage.own_questions[:] = [mine_question("Why?", 5, "ef" * 16), mine_question("Who pays?", 0, QID)]
    page = draw(homepage.client, "/")
    assert "Who pays for the carbon tax?" in feed(page) and "Tell me more" not in feed(page)
    assert "Why?" not in draw(homepage.client, "/my-posts")


# John, 9 November: on an issue page the Write/Ask box takes the place of "Write about this issue" and carries the
# issue to Home: a statement is written about it, and a question is asked about it (as the page's Ask box does).
SAME_SITE = {"sec-fetch-site": "same-origin"}
HOME_ASK = '<section class="ask home-ask" id="home-ask" data-ask'


def test_the_box_on_an_issue_page_takes_the_place_of_the_link(homepage):
    page = draw(homepage.client, "/issues/veto")
    assert '<form class="home-box" method="post" action="/home">' in page
    assert '<input type="hidden" name="issue" value="veto">' in page and "Write about this" not in page


def test_without_asking_the_issue_page_keeps_the_link(homepage, switch):
    switch(ask_enabled=False)
    page = draw(homepage.client, "/issues/veto")
    assert '<a class="write-issue" href="/?issue=veto">Write about this issue</a>' in page and "home-box" not in page


def test_the_box_carries_the_issue_to_home(homepage):
    page = homepage.client.post("/home", data={"start": "1", "text": "Rent caps help.", "issue": "veto"},
                                headers=SAME_SITE).text
    assert 'id="about-issue"' in page and 'data-start="/?issue=veto"' in page
    assert f'{HOME_ASK} data-issue="veto" hidden' in page and ">Rent caps help.</textarea>" in page


def test_a_gone_item_still_opens_home(homepage):
    page = homepage.client.post("/home", data={"start": "1", "text": "x y z", "issue": "gone"}, headers=SAME_SITE).text
    assert 'id="about-issue"' not in page and re.search(r' data-start[ >]', page)
    assert f"{HOME_ASK} hidden" in page and ">x y z</textarea>" in page


def test_a_reload_from_an_item_asks_about_it(homepage):
    page = draw(homepage.client, "/?issue=veto")
    assert f'{HOME_ASK} data-issue="veto" hidden' in page and "data-start" not in page
