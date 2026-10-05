from datetime import datetime, timezone

import pytest

from app import search


def test_every_word_is_required_as_written_or_as_a_start():
    """X4: "Try another word, or fewer words" is true only if every word must match."""
    assert search.lucene_query("Housing  Costs") == "+(housing housing*) +(costs costs*)"


@pytest.mark.parametrize("typed, query", [
    ('"quoted', '+(\\"quoted \\"quoted*)'),
    ("a:b", "+(a\\:b a\\:b*)"),
    ("c++", "+(c\\+\\+ c\\+\\+*)"),
    ("(veto)", "+(\\(veto\\) \\(veto\\)*)"),
    ("path/to", "+(path\\/to path\\/to*)"),
    ("back\\slash", "+(back\\\\slash back\\\\slash*)"),
    ("AND housing", "+(and and*) +(housing housing*)"),
    ("sub-issue", "+(sub\\-issue sub\\-issue*)"),
])
def test_lucene_query_escapes_everything(typed, query):
    assert search.lucene_query(typed) == query


@pytest.mark.parametrize("typed", ["", "   ", "*", "!!! ???", "-", "&& ||"])
def test_nothing_to_look_for(typed):
    assert search.lucene_query(typed) is None


def test_long_input_is_cut_to_ten_words_and_two_hundred_characters():
    assert search.lucene_query(" ".join(f"w{n}" for n in range(30))).count("*") == 10
    assert len(search.lucene_query("x" * 500)) < 2 * 200 + 10


ROWS = [
    {"label": "Issue", "key": "housing costs", "name": "Housing costs", "score": 3.0, "solution_homes": [], "evidence_homes": []},
    {"label": "Solution", "key": "social housing", "name": "Social housing", "score": 2.0,
     "solution_homes": ["housing costs"], "evidence_homes": []},
    {"label": "Evidence", "key": "report", "name": "Housing report", "score": 1.5, "solution_homes": [],
     "evidence_homes": ["housing costs"]},
    {"label": "Evidence", "key": "footnote", "name": "Housing footnote", "score": 1.0, "solution_homes": [],
     "evidence_homes": []},
]


def test_results_link_to_their_issue_pages():
    assert search.group(ROWS) == {
        "issues": [{"name": "Housing costs", "href": "/issues/housing%20costs"}],
        "solutions": [{"name": "Social housing", "href": "/issues/housing%20costs"}],
        "evidence": [{"name": "Housing report", "href": "/issues/housing%20costs"},
                     {"name": "Housing footnote", "href": None}]}


@pytest.fixture
def searching(member_app, monkeypatch):
    member_app.sign_in()
    asked = []
    monkeypatch.setattr("app.graph_search.search_names", lambda query: asked.append(query) or ROWS)
    monkeypatch.setattr("app.graph_search.search_posts", lambda query: [
        {"id": "p1", "text": "Rent is rising on our housing estate", "display_name": "Ada", "anonymous": False,
         "seed": False, "created_at": datetime.now(timezone.utc), "edited_at": None}])
    try:  # sub-plan D's module, which runs in parallel and may not be merged yet
        import app.graph_own_posts  # noqa: F401
        monkeypatch.setattr("app.graph_own_posts.post_flags", lambda me, ids: {})
    except ImportError:
        pass
    member_app.asked = asked
    return member_app


def test_the_issues_page_searches_and_groups(searching):
    page = searching.client.get("/issues?q=hous").text
    assert searching.asked == ["+(hous hous*)"]
    assert "Results for hous" in page
    for heading in ("<h3>Issues</h3>", "<h3>Solutions</h3>", "<h3>Evidence</h3>", "<h3>Posts</h3>"):
        assert heading in page
    assert '<a href="/issues/housing%20costs">Social housing</a>' in page
    assert "<li>Housing footnote</li>" in page
    assert "Rent is rising on our housing estate" in page
    assert '<a href="/issues">Show all issues</a>' in page
    assert 'placeholder="A word or two, for example: housing"' in page


def test_nothing_found_says_so(searching, monkeypatch):
    monkeypatch.setattr("app.graph_search.search_names", lambda query: [])
    monkeypatch.setattr("app.graph_search.search_posts", lambda query: [])
    assert "Nothing matches zebra. Try another word, or fewer words." in searching.client.get("/issues?q=zebra").text


def test_symbols_only_find_nothing_without_asking(searching):
    page = searching.client.get("/issues?q=%2A%2A%2A").text
    assert searching.asked == [] and "Nothing matches ***." in page


def test_an_empty_search_shows_the_list(searching):
    page = searching.client.get("/issues?q=").text
    assert "Results for" not in page and "Sort by" in page


def passphrase_only(member_app, monkeypatch):
    """The same app with ACCOUNTS_ENABLED unset, entered with the passphrase."""
    from dataclasses import replace
    off = replace(member_app.settings, accounts_enabled=False)
    monkeypatch.setattr("app.config.get_settings", lambda: off)
    monkeypatch.setattr("app.auth.get_settings", lambda: off)
    monkeypatch.setattr(member_app.main, "settings", off)
    member_app.client.post("/enter", data={"passphrase": "gate words"})


def test_search_works_behind_the_passphrase_too(searching, monkeypatch):
    passphrase_only(searching, monkeypatch)
    monkeypatch.setattr("app.graph_search.search_posts", lambda query: [])
    assert '<a href="/issues/housing%20costs">Housing costs</a>' in searching.client.get("/issues?q=housing").text
