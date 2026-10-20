"""X1: My Statements on Your account, the member's own posts with Edit and Delete. No database."""

from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def nobody_entered(monkeypatch):
    monkeypatch.setattr("app.graph_accounts.who_entered", lambda key: None)


def own(n, anonymous=False):
    return [{"id": f"p{i}", "text": f"Statement {i}", "display_name": None if anonymous else "Ada Tester",
             "anonymous": anonymous, "created_at": NOW - timedelta(minutes=i), "seed": False} for i in range(n)]


def test_with_no_posts_the_page_says_so(member_app):
    member_app.sign_in()
    page = member_app.client.get("/account").text
    assert '<h2 id="my-statements">My Statements</h2>' in page
    assert "You have not posted anything yet." in page
    assert "Show more" not in page


def test_own_posts_show_with_edit_and_delete_anonymous_ones_too(member_app):
    member_app.sign_in()
    member_app.own_posts.extend(own(1) + [dict(own(2, anonymous=True)[1], id="hidden", text="Said quietly")])
    page = member_app.client.get("/account").text
    assert "Statement 0" in page and "Said quietly" in page
    assert 'href="/posts/p0/edit"' in page and 'href="/posts/hidden/delete"' in page
    assert "Anonymous ·" in page
    assert page.index("My Statements") < page.index("Statement 0") < page.index("Said quietly")


def test_fifty_at_a_time_with_show_more(member_app):
    member_app.sign_in()
    member_app.own_posts.extend(own(120))
    page = member_app.client.get("/account").text
    assert "Statement 49<" in page and "Statement 50<" not in page
    assert 'href="/account?shown=100#my-statements">Show more</a>' in page
    page = member_app.client.get("/account?shown=100").text
    assert "Statement 99<" in page and 'href="/account?shown=150#my-statements"' in page
    page = member_app.client.get("/account?shown=150").text
    assert "Statement 119<" in page and "Show more" not in page
    # Odd values are kept within bounds rather than refused.
    assert "Statement 49<" in member_app.client.get("/account?shown=-5").text
