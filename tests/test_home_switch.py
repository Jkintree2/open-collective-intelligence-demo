"""v0.3's switch, HOME_ENABLED (off, preview or on). Off, every page is byte for byte the page drawn before v0.3:
the copies in tests/fixtures/pages_before_v03/, drawn from main before any v0.3 change, with Phase 3's four switches
on as the live site runs them. On, Home is for every signed-in member; preview, only for the members listed in
HOME_PREVIEW. The passphrase site (accounts off) keeps the old pages. No database.

A copy is refreshed only for a change agreed for the pages as they are with Home off:
OCI_REFRESH_V03_PAGES=1 python -m pytest tests/test_home_switch.py"""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import load_settings
from app.members import Member
from test_phase3_switches import ALL_ON, REQUIRED, draw, gate_in, pages  # noqa: F401  the same stubbed record

COPIES = Path(__file__).resolve().parent / "fixtures" / "pages_before_v03"
REFRESH = os.environ.get("OCI_REFRESH_V03_PAGES") == "1"
MEMBER_PAGES = {"write": "/", "issues": "/issues", "issue": "/issues/veto", "my_statements": "/my-statements",
                "about": "/about", "ask": "/ask"}
GATE_PAGES = {"gate_write": "/", "gate_issues": "/issues", "gate_issue": "/issues/veto", "gate_about": "/about",
              "gate_ask": "/ask"}
ADA = Member("acct:ada", "Ada Tester", "ada@example.org", False)
BOB = Member("acct:bob", "Bob Tester", "bob@example.org", False)


@pytest.fixture
def live_like(pages, monkeypatch):
    """The pages as the live site draws them: Phase 3's four switches on, no questions asked yet."""
    monkeypatch.setattr("app.graph_questions.recent", lambda issue, limit, **on: [])
    return pages


def compare(name, html):
    copy = COPIES / f"{name}.html"
    if REFRESH:
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(html, encoding="utf-8")
    assert html == copy.read_text(encoding="utf-8"), name


@pytest.mark.parametrize("name", MEMBER_PAGES)
def test_off_member_pages_unchanged(live_like, switch, name):
    live_like.sign_in()
    switch(**ALL_ON)
    compare(name, draw(live_like.client, MEMBER_PAGES[name]))


@pytest.mark.parametrize("name", GATE_PAGES)
def test_off_passphrase_pages_unchanged(live_like, switch, name):
    gate_in(live_like, switch, **ALL_ON)
    compare(name, draw(live_like.client, GATE_PAGES[name]))


def test_off_about_signed_out_unchanged(live_like, switch):
    switch(**ALL_ON)
    compare("about_signed_out", draw(live_like.client, "/about"))


def reader(member=None):
    """What home_on reads from a request: the member require_access found (None: signed out or passphrase)."""
    return SimpleNamespace(state=SimpleNamespace(member=member), cookies={})


def test_home_on_is_a_page_global(member_app):
    from app import home
    assert member_app.main.templates.env.globals["home_on"] is home.home_on


def test_off_is_off_for_everyone(switch):
    from app.home import home_on
    switch(home_preview=("ada@example.org",))
    assert [home_on(reader(ADA)), home_on(reader(BOB)), home_on(reader())] == [False, False, False]


def test_preview_only_listed_member(switch):
    from app.home import home_on
    switch(home_enabled="preview", home_preview=("ada@example.org",))
    assert home_on(reader(ADA)) is True
    assert home_on(reader(BOB)) is False
    assert home_on(reader()) is False
    switch(home_enabled="preview", home_preview=("ada@example.org",), accounts_enabled=False)
    assert home_on(reader()) is False


def test_preview_email_match_ignores_case(switch):
    from app.home import home_on
    switch(home_enabled="preview", home_preview=("ada@example.org",))
    assert home_on(reader(Member("acct:ada", "Ada Tester", "Ada@Example.ORG", False))) is True


def test_on_everyone_with_access(switch):
    from app.home import home_on
    switch(home_enabled="on")
    assert home_on(reader(ADA)) is True
    assert home_on(reader(BOB)) is True
    assert home_on(reader()) is False
    switch(home_enabled="on", accounts_enabled=False)
    assert home_on(reader()) is False


def test_bad_value_is_off():
    assert load_settings(REQUIRED).home_enabled == "off"
    for value, expected in (("on", "on"), (" ON ", "on"), ("preview", "preview"), ("Preview", "preview"),
                            ("off", "off"), ("", "off"), ("yes", "off"), ("true", "off"), ("1", "off")):
        assert load_settings({**REQUIRED, "HOME_ENABLED": value}).home_enabled == expected, value


def test_preview_list_is_lower_cased_and_trimmed():
    assert load_settings(REQUIRED).home_preview == ()
    settings = load_settings({**REQUIRED, "HOME_PREVIEW": " Ada@Example.org, ,bob@example.org "})
    assert settings.home_preview == ("ada@example.org", "bob@example.org")
