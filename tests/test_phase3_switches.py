"""Phase 3's four switches. Off, every page is byte for byte the page drawn before Phase 3 (the copies in
tests/fixtures/pages_before_phase3/, made from origin/p3-entries); on, through switches(), the menu items and
the card's script lines show. No database.

A copy is refreshed only for a change agreed for the pages as they are with every switch off:
OCI_REFRESH_PAGES=1 python -m pytest tests/test_phase3_switches.py"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import load_settings

COPIES = Path(__file__).resolve().parent / "fixtures" / "pages_before_phase3"
REFRESH = os.environ.get("OCI_REFRESH_PAGES") == "1"
SWITCHES = {"ask_enabled": "ASK_ENABLED", "follow_ups_enabled": "FOLLOW_UPS_ENABLED",
            "places_enabled": "PLACES_ENABLED", "about_enabled": "ABOUT_ENABLED"}
ALL_ON = {field: True for field in SWITCHES}
REQUIRED = {"DEMO_PASSPHRASE": "p", "SECRET_KEY": "s", "ADMIN_TOKEN": "a", "NEO4J_URI": "neo4j://x",
            "NEO4J_USERNAME": "neo4j", "NEO4J_PASSWORD": "p"}
POST = {"id": "p1", "text": "The veto blocks action.", "display_name": "Bob", "anonymous": False, "seed": False,
        "created_at": datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)}
ISSUE = {"key": "veto", "name": "Security Council veto", "parent_key": None, "parent_name": None, "children": []}
ISSUE_ROW = {"key": "veto", "name": "Security Council veto", "seed": False, "parent_key": None, "parent_name": None,
             "claims": 1, "people": 1, "person_keys": ["bob"], "solutions": 0, "evidence": 0, "evidence_keys": [],
             "last_activity": POST["created_at"]}
# Each page as the signed in member reads it; with accounts off, the passphrase pages.
MEMBER_PAGES = {"write": "/", "issues": "/issues", "issue": "/issues/veto", "my_statements": "/my-statements",
                "account": "/account"}
GATE_PAGES = {"gate_write": "/", "gate_issues": "/issues", "gate_issue": "/issues/veto"}
OUT_PAGES = {"sign_in": "/sign-in", "enter": "/enter"}


@pytest.fixture
def pages(member_app, switch, monkeypatch):
    """A record of one issue and one post, with times that do not move."""
    graph = member_app.main.graph
    monkeypatch.setattr(member_app.main, "relative_time", lambda then, now=None: "3 days ago")
    monkeypatch.setattr(graph, "list_posts", lambda limit: [dict(POST)])
    monkeypatch.setattr(graph, "list_issues", lambda: [dict(ISSUE_ROW)])
    monkeypatch.setattr(graph, "issue_posts", lambda key, limit: [dict(POST)])
    monkeypatch.setattr(graph, "issue_header", lambda key: dict(ISSUE) if key == "veto" else None)
    for name in ("issue_claimants", "issue_evidence"):
        monkeypatch.setattr(graph, name, lambda key: [])
    monkeypatch.setattr(graph, "issue_solutions", lambda key, me=None, ranked=False: [])
    monkeypatch.setattr("app.graph_accounts.who_entered", lambda key: None)
    # PLACES_ENABLED reads places (W4); none here.
    monkeypatch.setattr("app.graph_places.post_places", lambda ids: {})
    monkeypatch.setattr("app.graph_places.last_place", lambda me: None)
    monkeypatch.setattr("app.graph_places.issues_near", lambda country, area_key: set())
    member_app.own_posts.append(dict(POST))
    return member_app


def draw(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 200, (path, response.status_code)
    # The asset hash follows the static files, which Phase 3 adds to; the page around it must not change.
    return re.sub(r"\?v=[0-9a-f]{10}", "?v=ASSET", response.text)


def gate_in(pages, switch, **fields):
    """The site with the passphrase (accounts off), passed."""
    switch(accounts_enabled=False, **fields)
    pages.client.post("/enter", data={"passphrase": "gate words", "next": "/"}, follow_redirects=False)


def compare(name, html):
    copy = COPIES / f"{name}.html"
    if REFRESH:
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(html, encoding="utf-8")
    assert html == copy.read_text(encoding="utf-8"), name


def test_config_reads_each_switch_off_unless_set():
    off = load_settings(REQUIRED)
    assert [getattr(off, field) for field in SWITCHES] == [False] * 4
    for field, variable in SWITCHES.items():
        for value, expected in (("true", True), ("1", True), ("yes", True), ("", False), ("false", False), ("0", False)):
            assert getattr(load_settings({**REQUIRED, variable: value}), field) is expected, (variable, value)


def test_switches_reads_the_settings_when_the_page_is_drawn(pages, switch):
    main = pages.main
    assert main.templates.env.globals["switches"]() == {"ask": False, "follow_ups": False, "places": False,
                                                        "about": False}
    switch(ask_enabled=True, places_enabled=True)
    assert main.templates.env.globals["switches"]() == {"ask": True, "follow_ups": False, "places": True,
                                                        "about": False}


@pytest.mark.parametrize("name", MEMBER_PAGES)
def test_member_pages_are_unchanged_with_every_switch_off(pages, name):
    pages.sign_in()
    compare(name, draw(pages.client, MEMBER_PAGES[name]))


@pytest.mark.parametrize("name", GATE_PAGES)
def test_passphrase_pages_are_unchanged_with_every_switch_off(pages, switch, name):
    gate_in(pages, switch)
    compare(name, draw(pages.client, GATE_PAGES[name]))


def test_pages_outside_the_door_are_unchanged_with_every_switch_off(pages, switch):
    compare("sign_in", draw(pages.client, OUT_PAGES["sign_in"]))
    switch(accounts_enabled=False)
    compare("enter", draw(pages.client, OUT_PAGES["enter"]))


def nav(html):
    return re.search(r"<nav>.*?</nav>", html).group(0)


def test_the_menu_gains_ask_after_issues_and_about_last(pages, switch):
    pages.sign_in()
    switch(ask_enabled=True, about_enabled=True)
    assert nav(draw(pages.client, "/")) == (
        '<nav><a href="/">Write</a><a href="/issues">Issues</a><a href="/ask">Ask</a>'
        '<a href="/people">Enter a person</a><a href="/my-statements">My statements</a>'
        '<a href="/account">My account</a><a href="/about">About</a></nav>')


def test_with_the_passphrase_the_menu_shows_ask_and_about_too(pages, switch):
    gate_in(pages, switch, ask_enabled=True, about_enabled=True)
    assert nav(draw(pages.client, "/issues")) == (
        '<nav><a href="/">Write</a><a href="/issues">Issues</a><a href="/ask">Ask</a><a href="/about">About</a></nav>')


@pytest.mark.parametrize("field, item", [("ask_enabled", '<a href="/ask">Ask</a>'),
                                         ("about_enabled", '<a href="/about">About</a>')])
def test_each_menu_item_shows_only_with_its_own_switch(pages, switch, field, item):
    pages.sign_in()
    switch(**{other: True for other in ALL_ON if other != field})
    assert item not in draw(pages.client, "/")
    switch(**{field: True})
    assert item in draw(pages.client, "/")


SCRIPT = '<script src="/static/{}?v=ASSET" defer></script>'


@pytest.mark.parametrize("field, script", [("follow_ups_enabled", "followups.js"), ("places_enabled", "place.js")])
def test_each_card_script_loads_before_card_js_only_with_its_switch(pages, switch, field, script):
    pages.sign_in()
    switch(**{other: True for other in ALL_ON if other != field})
    assert SCRIPT.format(script) not in draw(pages.client, "/")
    switch(**{field: True})
    html = draw(pages.client, "/")
    assert html.index(SCRIPT.format(script)) < html.index(SCRIPT.format("card.js"))


def test_with_every_switch_on_the_write_page_only_gains_the_menu_items_and_two_scripts(pages, switch):
    pages.sign_in()
    before = draw(pages.client, "/")
    switch(**ALL_ON)
    after = draw(pages.client, "/")
    for added in ('<a href="/ask">Ask</a>', '<a href="/about">About</a>',
                  SCRIPT.format("followups.js"), SCRIPT.format("place.js")):
        after = after.replace(added, "", 1)
    assert after == before
