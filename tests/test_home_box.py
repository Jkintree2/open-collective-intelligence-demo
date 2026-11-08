"""v0.3: the Write/Ask box on Issues, My statements and About, and Home in the menu (John, 4 November: keep those
pages and their menu items; the box sits on them too). The box posts to /home with start set, and Home carries on
with the text. Signed out (About opens without signing in) there is no box. No database."""

import re

import pytest

from test_home_switch import live_like  # noqa: F401
from test_phase3_switches import ALL_ON, draw, pages  # noqa: F401

THREE = {"issues": "/issues", "my_statements": "/my-statements", "about": "/about"}
BOX = ('<form class="home-box" method="post" action="/home">\n'
       '  <input type="hidden" name="start" value="1">\n'
       '  <label for="home-box-text">Write what you think, or ask a question.</label>\n'
       '  <textarea id="home-box-text" name="text" rows="2" maxlength="4000" required></textarea>\n'
       '  <button type="submit" class="primary">Read my statement or question</button>\n'
       '</form>')
# John, 7 November: with Home on, My statements is "My posts".
HOME_MENU = ('<nav><a href="/">Home</a><a href="/issues">Issues</a><a href="/people">Enter a person</a>'
             '<a href="/my-posts">My posts</a><a href="/account">My account</a><a href="/about">About</a></nav>')
OLD_MENU = ('<nav><a href="/">Write</a><a href="/issues">Issues</a><a href="/ask">Ask</a><a href="/people">Enter a person</a>'
            '<a href="/my-statements">My statements</a><a href="/account">My account</a><a href="/about">About</a></nav>')


@pytest.fixture
def boxed(live_like, switch):
    live_like.sign_in()
    switch(**ALL_ON, home_enabled="on")
    return live_like


def nav(html):
    return re.search(r"<nav>.*?</nav>", html).group(0)


@pytest.mark.parametrize("name", THREE)
def test_box_on_three_pages_when_on(boxed, name):
    page = draw(boxed.client, THREE[name])
    assert page.count(BOX) == 1
    assert page.index("<h1") < page.index(BOX)


@pytest.mark.parametrize("path", ["/", "/issues/veto", "/ask"])
def test_no_small_box_on_home_the_issue_page_or_ask(boxed, path):
    assert "home-box" not in draw(boxed.client, path)


@pytest.mark.parametrize("name", THREE)
def test_no_box_when_off(live_like, switch, name):
    live_like.sign_in()
    switch(**ALL_ON)
    page = draw(live_like.client, THREE[name])
    assert "home-box" not in page and nav(page) == OLD_MENU


def test_no_box_with_ask_off(boxed, switch):
    switch(ask_enabled=False)
    for path in THREE.values():
        assert "home-box" not in draw(boxed.client, path), path


def test_about_signed_out_has_no_box(boxed):
    boxed.client.cookies.clear()
    page = draw(boxed.client, "/about")
    assert "home-box" not in page and '<a href="/">Home</a>' not in page


def test_menu_home_replaces_write_and_ask(boxed):
    for path in ("/", "/issues", "/my-statements", "/about", "/issues/veto", "/account"):
        assert nav(draw(boxed.client, path)) == HOME_MENU, path


def test_menu_unchanged_when_off(live_like, switch):
    live_like.sign_in()
    switch(**ALL_ON)
    assert nav(draw(live_like.client, "/")) == OLD_MENU


def test_preview_member_only(boxed, switch):
    switch(home_enabled="preview", home_preview=("ada@example.org",))
    page = draw(boxed.client, "/issues")
    assert BOX in page and nav(page) == HOME_MENU
    boxed.sign_in(key="acct:bob", name="Bob Tester", email="bob@example.org")
    page = draw(boxed.client, "/issues")
    assert "home-box" not in page and nav(page) == OLD_MENU


# Since John's 7 November email the record keeps who asked a question (Q56), so nothing is kept on the device and
# <body> names nobody, with Home on or off (tests/test_home_posts.py).
def body(html):
    return re.search(r"<body[^>]*>", html).group(0)


def test_body_names_nobody(boxed, switch):
    assert body(draw(boxed.client, "/")) == "<body>"
    switch(home_enabled="off")
    assert body(draw(boxed.client, "/")) == "<body>"
