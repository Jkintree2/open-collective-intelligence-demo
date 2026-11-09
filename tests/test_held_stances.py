"""John, 9 November 2026: "Your position" on the form starts at "no position" whatever the member already holds,
and "no position" never withdraws a stance; so beside a solution the member approves or opposes, the panel above the
form and the card's row say so (Q58). Offline: the reads are stubbed."""

import pytest

from app import graph_item_pages

VETO = {"key": "veto", "name": "Security Council veto", "parent_key": None, "parent_name": None, "children": []}
ABOLISH = {"key": "abolish the veto", "name": "Abolish the veto", "proposers": 1, "approves": 3, "opposes": 1,
           "evidence": []}
EXPAND = {**ABOLISH, "key": "expand the council", "name": "Expand the council"}


@pytest.fixture
def writer(member_app, monkeypatch):
    monkeypatch.setattr(member_app.main.graph, "issue_header", lambda key: VETO if key == "veto" else None)
    monkeypatch.setattr(member_app.main.graph, "issue_solutions", lambda key, *args, **kwargs: [dict(ABOLISH), dict(EXPAND)])
    monkeypatch.setattr(member_app.main.graph, "issue_evidence", lambda key: [])
    member_app.sign_in()
    return member_app


def test_the_panel_says_which_solutions_the_member_holds_a_stance_on(writer):
    writer.held.update({"abolish the veto": "approve", "expand the council": "oppose"})
    page = writer.client.get("/?issue=veto").text
    first, second = page.split('<div class="about-solution">')[1:3]
    assert '</fieldset>\n    <p class="held-note">You approve this already.</p>\n  </div>' in first
    assert '<p class="held-note">You oppose this already.</p>' in second


def test_without_a_stance_the_panel_is_as_before(writer):
    writer.held.update({"expand the council": "approve"})
    page = writer.client.get("/?issue=veto").text
    first = page.split('<div class="about-solution">')[1]
    assert "held-note" not in first and "</fieldset>\n  </div>" in first


def test_the_panel_for_a_solution_says_it_too(writer, monkeypatch):
    monkeypatch.setattr(graph_item_pages, "solution", lambda key, me=None: {
        **ABOLISH, "proposed_by": ["Ada Tester"], "my_stance": None, "evidence": [],
        "issues": [{"key": "veto", "name": "Security Council veto", "parent_key": None, "parent_name": None}]})
    writer.held.update({"abolish the veto": "oppose"})
    assert '<p class="held-note">You oppose this already.</p>' in writer.client.get("/?solution=abolish%20the%20veto").text


def test_the_card_gets_the_members_own_stances(writer):
    writer.held.update({"abolish the veto": "approve"})
    answer = writer.client.get("/api/candidates").json()
    assert answer["held"] == {"abolish the veto": "approve"}
    assert set(answer) >= {"issues", "solutions", "evidence", "held"}
