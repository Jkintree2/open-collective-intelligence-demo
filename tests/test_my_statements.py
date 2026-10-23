"""X1: My statements, the member's own posts with Edit and Delete, on a page of its own since John's 22 Oct email. No database."""

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
    page = member_app.client.get("/my-statements").text
    assert "<h1>My statements</h1>" in page
    assert "You have not posted anything yet." in page
    assert "Show more" not in page


def test_own_posts_show_with_edit_and_delete_anonymous_ones_too(member_app):
    member_app.sign_in()
    member_app.own_posts.extend(own(1) + [dict(own(2, anonymous=True)[1], id="hidden", text="Said quietly")])
    page = member_app.client.get("/my-statements").text
    assert "Statement 0" in page and "Said quietly" in page
    assert 'href="/posts/p0/edit"' in page and 'href="/posts/hidden/delete"' in page
    assert "Anonymous ·" in page
    assert page.index("<h1>My statements</h1>") < page.index("Statement 0") < page.index("Said quietly")


def test_fifty_at_a_time_with_show_more(member_app):
    member_app.sign_in()
    member_app.own_posts.extend(own(120))
    page = member_app.client.get("/my-statements").text
    assert "Statement 49<" in page and "Statement 50<" not in page
    assert 'href="/my-statements?shown=100">Show more</a>' in page
    page = member_app.client.get("/my-statements?shown=100").text
    assert "Statement 99<" in page and 'href="/my-statements?shown=150"' in page
    page = member_app.client.get("/my-statements?shown=150").text
    assert "Statement 119<" in page and "Show more" not in page
    # Odd values are kept within bounds rather than refused.
    assert "Statement 49<" in member_app.client.get("/my-statements?shown=-5").text


def test_a_shown_that_is_not_a_number_is_the_first_page(member_app):
    member_app.sign_in()
    member_app.own_posts.extend(own(60))
    response = member_app.client.get("/my-statements?shown=abc")
    assert response.status_code == 200 and "Statement 49<" in response.text and "Statement 50<" not in response.text


def test_show_more_stops_at_the_most_the_page_holds(member_app, monkeypatch):
    monkeypatch.setattr("app.routes_accounts.STATEMENTS_MAX", 100)
    member_app.sign_in()
    member_app.own_posts.extend(own(130))
    page = member_app.client.get("/my-statements?shown=100").text
    assert "Statement 99<" in page and "Show more" not in page


def test_my_account_no_longer_lists_the_posts(member_app):
    member_app.sign_in()
    member_app.own_posts.extend(own(1))
    page = member_app.client.get("/account").text
    assert "Statement 0" not in page and "My Statements" not in page


def test_the_page_needs_a_signed_in_member(member_app):
    assert member_app.client.get("/my-statements", follow_redirects=False).status_code == 303
