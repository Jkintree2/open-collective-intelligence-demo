"""John's "Asking" email, 11 November 2026: the link that posts a statement with no issue read like a plain Post, and
nothing on the card said the statement would be listed under no issue. The words are 04_interface.md's; the line on
the card is card.js's (tests/test_card_plain.cjs)."""

from pathlib import Path

import pytest

from test_home_switch import live_like  # noqa: F401
from test_phase3_switches import ALL_ON, draw, pages  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
INTERFACE = (ROOT / "docs" / "planning" / "04_interface.md").read_text(encoding="utf-8")
CARD_JS = (ROOT / "app" / "static" / "card.js").read_text(encoding="utf-8")
LINK = "Post my words only, without an issue"
PLAIN = "Your statement will be posted on its own. It will not be listed under any issue."


@pytest.mark.parametrize("home", ["on", "off"])
def test_the_link_says_the_words_go_without_an_issue(live_like, switch, home):
    live_like.sign_in()
    switch(**ALL_ON, home_enabled=home)
    page = draw(live_like.client, "/")
    assert f'<button type="button" id="plain" class="quiet">{LINK}</button>' in page
    assert "post it as a plain statement anyway" not in page


def test_the_words_match_04_interface():
    assert f'"{LINK}"' in INTERFACE and f'"{PLAIN}"' in INTERFACE
    assert f"'{PLAIN}'" in CARD_JS
