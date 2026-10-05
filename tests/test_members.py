import pytest

from app import accounts

PAGES = ["/", "/issues", "/feed", "/?issue=veto"]


@pytest.mark.parametrize("path", PAGES)
def test_with_accounts_on_every_page_sends_a_stranger_to_sign_in(member_app, path):
    result = member_app.client.get(path, follow_redirects=False)
    assert result.status_code == 303
    assert result.headers["location"].startswith("/sign-in?next=")


def test_the_card_api_asks_for_sign_in_again(member_app):
    result = member_app.client.get("/api/candidates")
    assert result.status_code == 401
    assert result.json() == {"message": "Please sign in again.", "redirect": "/sign-in"}


def test_the_passphrase_no_longer_opens_the_door(member_app):
    client = member_app.client
    assert client.get("/enter", follow_redirects=False).headers["location"].startswith("/sign-in")
    client.post("/enter", data={"passphrase": "gate words"})
    assert client.get("/", follow_redirects=False).status_code == 303


def test_a_signed_in_member_reads_every_page(member_app):
    member_app.sign_in()
    for path in PAGES:
        assert member_app.client.get(path, follow_redirects=False).status_code == 200


@pytest.mark.parametrize("change", ["switched_off", "new_password", "forged"])
def test_a_cookie_stops_working_when_the_record_says_so(member_app, change):
    row = member_app.sign_in()
    if change == "switched_off":
        member_app.accounts.clear()  # Q13 returns nothing for an inactive or unaccepted account
    elif change == "new_password":
        row["password_hash"] = "scrypt$another-hash"
    else:
        member_app.set_cookie(accounts.make_member_cookie("acct:ada", "scrypt$fixture-hash", "wrong secret"))
    assert member_app.client.get("/", follow_redirects=False).status_code == 303


CROSS_SITE = ({"Origin": "https://other.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"},
              {"Referer": "https://other.example/page"})


def test_a_post_from_another_site_is_refused(member_app):
    member_app.sign_in()
    for headers in CROSS_SITE:
        result = member_app.client.post("/api/posts", json={"text": "Hello", "plain": True}, headers=headers)
        assert result.status_code == 403
        assert result.json() == {"message": "Please reload the page and try again."}
        page = member_app.client.post("/posts", data={"text": "Hello"}, headers=headers)
        assert page.status_code == 403 and "Please reload the page and try again." in page.text
        assert "detail" not in page.text
    assert member_app.client.post("/api/posts", json={"text": "Hello", "plain": True},
                                  headers={"Referer": "http://testserver/"}).status_code == 201
    assert len(member_app.writes) == 1


def test_a_browser_that_says_same_origin_is_let_through(member_app):
    """A page sent with a strict referrer policy can post `Origin: null`; the browser's own
    Sec-Fetch-Site says where the form came from, and a page cannot forge it."""
    member_app.sign_in()
    result = member_app.client.post("/api/posts", json={"text": "Hello", "plain": True},
                                    headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"})
    assert result.status_code == 201


def test_other_sites_are_refused_with_accounts_off_too(member_app, monkeypatch):
    """The check on /posts and /api/* does not depend on ACCOUNTS_ENABLED."""
    from dataclasses import replace
    off = replace(member_app.settings, accounts_enabled=False)
    for target in ("app.config.get_settings", "app.auth.get_settings"):
        monkeypatch.setattr(target, lambda: off)
    monkeypatch.setattr(member_app.main, "settings", off)
    member_app.client.post("/enter", data={"passphrase": "gate words"})
    for headers in CROSS_SITE:
        result = member_app.client.post("/api/posts", json={"text": "Hello", "plain": True}, headers=headers)
        assert result.status_code == 403 and result.json() == {"message": "Please reload the page and try again."}
    assert member_app.writes == []
    assert member_app.client.post("/api/posts", json={"text": "Hello", "plain": True}).status_code == 201


def test_a_signed_out_page_script_is_told_to_sign_in_again(member_app):
    """A form a page script sends with Accept: application/json (stances.js, sub-plan C) gets JSON,
    not a redirect to an HTML page it cannot read."""
    result = member_app.client.post("/posts", data={"text": "Hello"}, headers={"Accept": "application/json"},
                                    follow_redirects=False)
    assert result.status_code == 401
    assert result.json() == {"message": "Please sign in again.", "redirect": "/sign-in"}
