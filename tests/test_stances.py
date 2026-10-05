import pytest

ISSUE = {"key": "veto", "name": "Security Council veto", "parent_key": None, "parent_name": None,
         "children": [], "created_at": None, "seed": False}
# Today's "Proposed solutions" section for one solution, rendered from issue.html at phase-1 c48bfe5.
TODAY_SOLUTIONS = ('<h2>Proposed solutions</h2>\n\n<section class="solution">\n  <h3>Abolish the veto</h3>\n'
                   '  <p class="counts">proposed by 1 · approved by 2 · opposed by 1</p>\n  \n  \n  \n  \n'
                   '</section>\n\n\n')


@pytest.fixture
def issue_page(member_app, monkeypatch):
    g = member_app.main.graph
    mine = {"value": None}
    asked = []
    monkeypatch.setattr(g, "issue_header", lambda key: ISSUE if key == "veto" else None)
    monkeypatch.setattr(g, "issue_claimants", lambda key: {"claims": 0, "people": 0, "names": []})
    monkeypatch.setattr(g, "issue_evidence", lambda key: [])
    monkeypatch.setattr(g, "issue_posts", lambda key, limit: [])

    def issue_solutions(key, me=None, ranked=False):
        asked.append({"me": me, "ranked": ranked})
        return [{"key": "abolish the veto", "name": "Abolish the veto", "proposers": 1, "approves": 2, "opposes": 1,
                 "my_stance": mine["value"] if me else None, "evidence": []}]
    monkeypatch.setattr(g, "issue_solutions", issue_solutions)
    calls = []
    monkeypatch.setattr("app.graph_stances.set_stance", lambda person, solution, stance, now:
                        calls.append((person, solution, stance)) or
                        (None if solution == "nowhere" else {"approves": 3, "opposes": 1, "my_stance": "APPROVE"}))
    member_app.mine, member_app.calls, member_app.asked = mine, calls, asked
    return member_app


def test_a_member_sees_both_buttons_and_the_ranking_line(issue_page):
    issue_page.sign_in()
    page = issue_page.client.get("/issues/veto").text
    assert issue_page.asked[-1] == {"me": "acct:ada", "ranked": True}
    assert "Listed by approvals minus oppositions." in page
    assert f'/static/stances.js?v={issue_page.main.templates.env.globals["asset_version"]}' in page
    assert 'id="solution-abolish-the-veto"' in page
    assert 'action="/solutions/abolish%20the%20veto/stance"' in page
    assert 'name="choice" value="approve" aria-pressed="false">Approve</button>' in page
    assert 'name="choice" value="oppose" aria-pressed="false">Oppose</button>' in page
    assert "approved by <span data-approves>2</span> · opposed by <span data-opposes>1</span>" in page


@pytest.mark.parametrize("held, approve, oppose, line", [
    ("APPROVE", 'value="withdraw" aria-pressed="true">Approve', 'value="oppose" aria-pressed="false">Oppose',
     "You approve this. Press Approve again to withdraw."),
    ("OPPOSE", 'value="approve" aria-pressed="false">Approve', 'value="withdraw" aria-pressed="true">Oppose',
     "You oppose this. Press Oppose again to withdraw."),
])
def test_the_held_stance_is_highlighted_and_pressing_it_withdraws(issue_page, held, approve, oppose, line):
    issue_page.sign_in()
    issue_page.mine["value"] = held
    page = issue_page.client.get("/issues/veto").text
    assert approve in page and oppose in page and line in page


def test_pressing_a_button_without_javascript_comes_back_to_the_solution(issue_page):
    issue_page.sign_in()
    result = issue_page.client.post("/solutions/abolish the veto/stance", data={"choice": "approve", "issue": "veto"},
                                    follow_redirects=False)
    assert result.status_code == 303 and result.headers["location"] == "/issues/veto#solution-abolish-the-veto"
    assert issue_page.calls == [("acct:ada", "abolish the veto", "approve")]


@pytest.mark.parametrize("choice, stance", [("approve", "approve"), ("oppose", "oppose"), ("withdraw", None)])
def test_the_page_script_gets_the_new_counts(issue_page, choice, stance):
    issue_page.sign_in()
    result = issue_page.client.post("/solutions/abolish the veto/stance", data={"choice": choice, "issue": "veto"},
                                    headers={"Accept": "application/json"})
    assert result.json() == {"approves": 3, "opposes": 1, "my_stance": "APPROVE"}
    assert issue_page.calls[-1][2] == stance


def test_an_unknown_solution_or_choice_is_not_saved(issue_page):
    issue_page.sign_in()
    json_headers = {"Accept": "application/json"}
    result = issue_page.client.post("/solutions/nowhere/stance", data={"choice": "approve", "issue": "veto"},
                                    headers=json_headers)
    assert result.status_code == 404 and result.json() == {"message": "Your position was not saved. Please try again."}
    result = issue_page.client.post("/solutions/abolish/stance", data={"choice": "maybe", "issue": "veto"},
                                    headers=json_headers)
    assert result.status_code == 422 and result.json() == {"message": "Your position was not saved. Please try again."}
    assert issue_page.calls == [("acct:ada", "nowhere", "approve")]


def test_a_failure_without_javascript_comes_back_to_the_solution(issue_page):
    """Item 17 of the 5 October review: never a JSON body on a page."""
    issue_page.sign_in()
    for data in ({"choice": "maybe", "issue": "veto"}, {"choice": "approve", "issue": "veto"}):
        path = "/solutions/abolish the veto/stance" if data["choice"] == "maybe" else "/solutions/nowhere/stance"
        result = issue_page.client.post(path, data=data, follow_redirects=False)
        assert result.status_code == 303 and result.headers["location"].startswith("/issues/veto?not_saved=")
    page = issue_page.client.get("/issues/veto?not_saved=abolish%20the%20veto").text
    assert "Your position was not saved. Please try again.</p>" in page and "detail" not in page


def test_strangers_other_sites_and_accounts_off(issue_page, monkeypatch):
    client = issue_page.client
    assert client.post("/solutions/abolish/stance", data={"choice": "approve"}, follow_redirects=False).status_code == 303
    signed_out = client.post("/solutions/abolish/stance", data={"choice": "approve"}, headers={"Accept": "application/json"})
    assert signed_out.status_code == 401 and signed_out.json()["redirect"] == "/sign-in"
    issue_page.sign_in()
    other = client.post("/solutions/abolish/stance", data={"choice": "approve"}, headers={"Origin": "https://other.example"})
    assert other.status_code == 403 and "Please reload the page and try again." in other.text and "detail" not in other.text
    from dataclasses import replace
    monkeypatch.setattr("app.config.get_settings", lambda: replace(issue_page.settings, accounts_enabled=False))
    assert client.post("/solutions/abolish/stance", data={"choice": "approve"}).status_code == 404
    assert issue_page.calls == []


def test_without_accounts_the_issue_page_is_todays(issue_page, monkeypatch):
    """X1: with ACCOUNTS_ENABLED unset the solutions section is byte for byte today's, in today's order,
    and no stance script loads."""
    from dataclasses import replace
    off = replace(issue_page.settings, accounts_enabled=False)
    monkeypatch.setattr("app.config.get_settings", lambda: off)
    monkeypatch.setattr("app.auth.get_settings", lambda: off)
    monkeypatch.setattr(issue_page.main, "settings", off)
    issue_page.client.post("/enter", data={"passphrase": "gate words"})
    page = issue_page.client.get("/issues/veto").text
    assert issue_page.asked[-1] == {"me": None, "ranked": False}
    assert page[page.index("<h2>Proposed solutions</h2>"):page.index("<h2>Evidence about this issue</h2>")] == TODAY_SOLUTIONS
    assert '<main class="column">\n    \n<p class="crumbs">' in page  # nothing on the content block's first line
    assert "stances.js" not in page and "Listed by" not in page


def test_a_post_by_an_account_takes_the_one_stance_rule_and_a_passphrase_post_does_not(member_app, monkeypatch):
    """X1: with accounts off, a passphrase post writes today's stance statement."""
    card = {"text": "I oppose abolishing the veto", "issues": [{"name": "Flooding"}]}
    member_app.sign_in()
    assert member_app.client.post("/api/posts", json=card).status_code == 201
    assert member_app.writes[-1][1]["one_stance"] is True
    from dataclasses import replace
    off = replace(member_app.settings, accounts_enabled=False)
    for target in ("app.config.get_settings", "app.auth.get_settings"):
        monkeypatch.setattr(target, lambda: off)
    monkeypatch.setattr(member_app.main, "settings", off)
    member_app.client.post("/enter", data={"passphrase": "gate words"})
    assert member_app.client.post("/api/posts", json=card).status_code == 201
    assert member_app.writes[-1][1]["one_stance"] is False


def test_template_anchor_filter_is_the_route_anchor_rule(member_app):
    from app.routes_stances import solution_anchor
    assert member_app.main.templates.env.filters["anchor"] is solution_anchor
    assert member_app.main.templates.env.filters["anchor"]("more bike lanes") == "solution-more-bike-lanes"
