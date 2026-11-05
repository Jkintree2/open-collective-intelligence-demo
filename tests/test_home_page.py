"""v0.3: the Home page as it is drawn with HOME_ENABLED on. One box takes a statement or a question; the words are
04_interface.md's ("v0.3: Write and Ask on one Home page"). With ASK_ENABLED off nothing mentions asking, and the
edit page stays a plain write form. No database."""

from pathlib import Path

import pytest

from app.config import HOME_SENTENCE, SITE_SENTENCE
from test_home_switch import live_like  # noqa: F401
from test_own_posts import owned  # noqa: F401  a member's own post, for the edit page
from test_phase3_switches import ALL_ON, draw, pages  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
INTERFACE = (ROOT / "docs" / "planning" / "04_interface.md").read_text(encoding="utf-8")
HOME_JS = ROOT / "app" / "static" / "home.js"
LABEL = "Write or dictate your statement or question in the box."
BUTTON = "Read my statement or question"
UNSURE = "Is this a statement to post, or a question to ask?"
TO_STATEMENT, TO_QUESTION = "Post it as a statement instead", "Ask it as a question instead"


@pytest.fixture
def homepage(live_like, switch):
    live_like.sign_in()
    switch(**ALL_ON, home_enabled="on")
    return live_like


def test_home_page_has_one_box_for_both(homepage):
    page = draw(homepage.client, "/")
    assert f'<p class="sentence">{HOME_SENTENCE}</p>' in page and SITE_SENTENCE not in page
    assert f'<label for="text">{LABEL}</label>' in page
    assert f'id="read">{BUTTON}</button>' in page
    assert 'action="/home"' in page and " data-home data-home-ask" in page and "data-start" not in page
    assert '<button type="button" id="home-switch" class="quiet home-switch" hidden></button>' in page
    assert 'id="home-ask" data-ask hidden' in page and "data-ask-status" in page and "data-ask-answers" in page
    assert f"<p>{UNSURE}</p>" in page


def test_home_page_loads_ask_and_home_after_app(homepage):
    page = draw(homepage.client, "/")
    scripts = ['<script src="/static/app.js?v=ASSET" defer></script>',
               '<script src="/static/ask.js?v=ASSET" defer></script>',
               '<script src="/static/home.js?v=ASSET" defer></script>']
    assert [page.index(script) for script in scripts] == sorted(page.index(script) for script in scripts)


def test_editing_is_plain_write_form(owned, switch, monkeypatch):
    """Review Focus 4: the edit page draws index.html with `editing`; it stays the write form it was."""
    from app.extract import Candidates
    monkeypatch.setattr(owned.main.graph, "candidates", Candidates.empty)
    switch(**ALL_ON, home_enabled="on")
    page = owned.client.get("/posts/mine-1/edit").text
    assert 'action="/posts/mine-1/edit"' in page and ">Save changes</button>" in page
    for absent in ("data-home", "/home", "home.js", "home-ask", "home-unsure", "home-switch", LABEL, BUTTON,
                   "My most recent"):
        assert absent not in page, absent


def test_ask_off_no_ask_wording(homepage, switch):
    """Review Focus 5: Home on, ASK_ENABLED off: the box only posts, and nothing mentions asking."""
    switch(ask_enabled=False)
    page = draw(homepage.client, "/")
    assert f'<p class="sentence">{SITE_SENTENCE}</p>' in page
    assert '<label for="text">Write or dictate your statement in the box.</label>' in page
    assert 'action="/home"' in page and " data-home" in page
    for absent in ("data-home-ask", "ask a question", "home.js", "ask.js", "home-ask", "home-unsure", "home-switch",
                   BUTTON, UNSURE, "Ask it", "Questions people are asking"):
        assert absent not in page, absent


def test_wording_strings_match_04_interface():
    for line in (HOME_SENTENCE, LABEL, BUTTON, UNSURE, "Post it", "Ask it", TO_STATEMENT, TO_QUESTION,
                 "My most recent statements and questions", "Home · Issues · Enter a person"):
        assert line in INTERFACE, line
    script = HOME_JS.read_text(encoding="utf-8")
    assert f"'{TO_STATEMENT}'" in script and f"'{TO_QUESTION}'" in script


# Task 5: the writer's own recent statements under the button; with JavaScript, home.js adds the questions asked on
# this device (tests/test_home.cjs). Others' questions show as on Ask the database.
def own(number, minutes_ago):
    from datetime import datetime, timedelta, timezone
    return {"id": f"mine-{number}", "text": f"My statement number {number}.", "display_name": "Ada Tester",
            "anonymous": False, "seed": False,
            "created_at": datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc) - timedelta(minutes=minutes_ago)}


def mine_list(page):
    import re
    found = re.search(r'<ul id="home-mine">(.*?)</ul>', page, re.S)
    return re.findall(r'<li data-at="([^"]+)" data-kind="statement"><a href="/my-statements">([^<]*)</a>', found.group(1))


def test_my_recent_statements_under_the_box(homepage):
    homepage.own_posts[:] = [own(n, n) for n in range(1, 8)]
    page = draw(homepage.client, "/")
    assert "<h2>My most recent statements and questions</h2>" in page
    assert mine_list(page) == [("2026-11-05T11:59:00Z", "My statement number 1."),
                               ("2026-11-05T11:58:00Z", "My statement number 2."),
                               ("2026-11-05T11:57:00Z", "My statement number 3."),
                               ("2026-11-05T11:56:00Z", "My statement number 4."),
                               ("2026-11-05T11:55:00Z", "My statement number 5.")]
    assert page.index('id="read"') < page.index('id="home-mine"') < page.index('id="feed"')


def test_a_long_statement_is_cut_in_the_list(homepage):
    homepage.own_posts[:] = [{**own(1, 1), "text": "word " * 60}]
    (_, text), = mine_list(draw(homepage.client, "/"))
    assert len(text) <= 121 and text.endswith("…")


def test_the_list_waits_hidden_when_there_is_nothing_yet(homepage):
    homepage.own_posts.clear()
    page = draw(homepage.client, "/")
    assert '<section class="home-mine" id="home-mine-section" hidden>' in page


def test_with_ask_off_the_list_is_statements_only(homepage, switch):
    switch(ask_enabled=False)
    page = draw(homepage.client, "/")
    assert "<h2>My most recent statements</h2>" in page and "and questions" not in page


def test_questions_people_are_asking_on_home(homepage, monkeypatch):
    listed = [{"text": "Why do people oppose the carbon tax?", "issue_key": "climate", "issue_name": "Climate",
               "id": "ab" * 16, "answered": True},
              {"text": "Is the veto fair?", "issue_key": None, "issue_name": None, "id": None, "answered": False}]
    monkeypatch.setattr("app.graph_questions.recent", lambda issue, limit, **on: listed)
    page = draw(homepage.client, "/")
    assert "<h3>Questions people are asking</h3>" in page
    assert f'<a class="ask-answered" href="/ask/answers/{"ab" * 16}">Why do people oppose the carbon tax?</a>' in page
    assert '<span class="counts">On <a href="/issues/climate">Climate</a></span>' in page
    assert '<button type="button" class="home-again">Is the veto fair?</button>' in page
    assert page.index("Questions people are asking") < page.index('id="feed"')


def test_gate_reader_has_no_list(live_like, switch):
    from test_phase3_switches import gate_in
    gate_in(live_like, switch, **ALL_ON, home_enabled="on")
    page = draw(live_like.client, "/")
    assert "home-mine" not in page and "Questions people are asking" not in page and "data-home" not in page
