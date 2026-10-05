"""Static checks on app.css for the Phase 1 forms at 360 px: iOS zooms into any input under 16 px,
and a touch target needs 44 px."""
import re
from pathlib import Path

import pytest

CSS = Path("app/static/app.css").read_text(encoding="utf-8")


def rule(selector_part):
    """The declarations of every rule whose selector list mentions `selector_part`."""
    return " ".join(body for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", CSS) if selector_part in selectors)


@pytest.mark.parametrize("kind", ["email", "search"])
def test_email_and_search_inputs_look_like_the_other_text_inputs(kind):
    selector = f'input[type="{kind}"]'
    assert selector in CSS
    assert "height: 40px" in rule(selector) and "font: inherit" in rule(selector)


def test_selects_outside_the_card_are_full_size():
    body = rule("main select")
    assert "min-height: 44px" in body and "font: inherit" in body


def test_quiet_links_are_tall_enough_to_tap():
    body = rule("a.quiet")
    assert "inline-flex" in body and "align-items: center" in body and "min-height: 44px" in body


def test_the_header_links_wrap_on_a_narrow_phone():
    nav = " ".join(body for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", CSS)
                   if selectors.strip() == ".site-header nav")
    assert "flex-wrap: wrap" in nav and "nowrap" not in nav
