"""Phase 3, places in the record (W4): the place under a post (Q44) and the Issues page's Near filter (Q43),
behind PLACES_ENABLED. No database: graph_places is stubbed; the live set is tests/test_live_places.py."""

import json
import logging
import re
from datetime import datetime, timezone

import pytest

WHEN = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def post(post_id, text="The veto blocks action."):
    return {"id": post_id, "text": text, "display_name": "Bob", "anonymous": False, "seed": False, "created_at": WHEN}


def issue(key, name, people, parent=None, claims=1):
    return {"key": key, "name": name, "seed": False, "parent_key": parent, "parent_name": None, "claims": claims,
            "people": people, "person_keys": [f"p{n}" for n in range(people)], "solutions": 0, "evidence": 0,
            "evidence_keys": [], "last_activity": WHEN}


RECORD = [issue("veto", "Security Council veto", 3), issue("flooding", "Flooding", 2),
          issue("berlin floods", "Floods in Berlin", 1, parent="flooding"),
          issue("coast floods", "Coastal floods", 4, parent="flooding"), issue("rent", "Rent", 1)]


@pytest.fixture
def site(member_app, switch, monkeypatch):
    """The member app with a small record; `asked` collects every place read."""
    graph = member_app.main.graph
    asked = {"post_places": [], "issues_near": [], "last_place": []}
    member_app.asked, member_app.near_keys, member_app.last = asked, set(), None
    member_app.places = {"p1": {"id": "p1", "country": "US", "area": "St. Louis"},
                         "p2": {"id": "p2", "country": "DE", "area": None}}
    monkeypatch.setattr(graph, "list_posts", lambda limit: [post("p1"), post("p2"), post("p3")])
    monkeypatch.setattr(graph, "list_issues", lambda: [dict(row) for row in RECORD])

    def post_places(ids):
        asked["post_places"].append(list(ids))
        return {i: member_app.places[i] for i in ids if i in member_app.places}

    def issues_near(country, area_key):
        asked["issues_near"].append((country, area_key))
        return set(member_app.near_keys)

    def last_place(me):
        asked["last_place"].append(me)
        return member_app.last

    monkeypatch.setattr("app.graph_places.post_places", post_places)
    monkeypatch.setattr("app.graph_places.issues_near", issues_near)
    monkeypatch.setattr("app.graph_places.last_place", last_place)
    member_app.switch = switch
    return member_app


def place_lines(html):
    return re.findall(r'<p class="place">(.*?)</p>', html)


def issue_names(html):
    return re.findall(r'<h2><a href="/issues/[^"]+">(.*?)</a></h2>', html)


def selected(html):
    found = re.search(r'<option value="([A-Z]*)" selected>', html)
    return found.group(1) if found else ""


def area_value(html):
    return re.search(r'<input id="near-area" name="area" type="text" value="(.*?)"', html).group(1)


# Off: nothing is read and nothing shows.

def test_off_no_place_is_read_or_shown(site):
    site.sign_in()
    html = site.client.get("/").text
    assert place_lines(html) == [] and site.asked["post_places"] == []
    issues = site.client.get("/issues?country=US&area=St+Louis").text
    assert 'class="near"' not in issues and "Issues near" not in issues
    assert issue_names(issues) == issue_names(site.client.get("/issues").text)
    assert site.asked == {"post_places": [], "issues_near": [], "last_place": []}


# Under a post (Q44).

def test_a_placed_post_says_where_once_per_list(site):
    site.sign_in()
    site.switch(places_enabled=True)
    html = site.client.get("/").text
    assert place_lines(html) == ["In St. Louis, United States", "In Germany"]
    assert site.asked["post_places"] == [["p1", "p2", "p3"]]
    # Under the statement, before the chips and the list of what was added.
    article = html[html.index('<article class="post">'):html.index("</article>")]
    assert article.index('class="statement"') < article.index('class="place"')


def test_my_statements_show_the_place_too(site):
    site.sign_in()
    site.switch(places_enabled=True)
    site.own_posts.extend([post("p2"), post("p3")])
    assert place_lines(site.client.get("/my-statements").text) == ["In Germany"]


def test_the_place_is_escaped(site):
    site.sign_in()
    site.switch(places_enabled=True)
    site.places["p1"]["area"] = "<b>Town</b>"
    assert place_lines(site.client.get("/").text)[0] == "In &lt;b&gt;Town&lt;/b&gt;, United States"


# The Near filter's prefill (Q43).

def test_the_form_starts_at_the_members_last_placed_post(site):
    site.sign_in()
    site.switch(places_enabled=True)
    site.last = {"country": "US", "area": "St. Louis"}
    html = site.client.get("/issues").text
    assert selected(html) == "US" and area_value(html) == "St. Louis"
    assert site.asked["last_place"] == ["acct:ada"] and site.asked["issues_near"] == []
    # Starting the form filters nothing: the whole list shows.
    assert "Issues near" not in html and len(issue_names(html)) == 3


def test_with_no_placed_post_the_form_starts_at_the_accounts_country(site):
    site.sign_in()
    site.accounts["acct:ada"]["country"] = "USA"
    site.switch(places_enabled=True)
    html = site.client.get("/issues").text
    assert selected(html) == "US" and area_value(html) == ""


def test_an_unknown_account_country_starts_empty(site):
    site.sign_in()
    site.accounts["acct:ada"]["country"] = "Atlantis"
    site.switch(places_enabled=True)
    html = site.client.get("/issues").text
    assert selected(html) == "" and '<option value=""></option>' in html


def test_with_the_passphrase_the_form_starts_empty(site):
    site.switch(accounts_enabled=False, places_enabled=True)
    site.client.post("/enter", data={"passphrase": "gate words", "next": "/"}, follow_redirects=False)
    html = site.client.get("/issues").text
    assert 'class="near"' in html and selected(html) == "" and site.asked["last_place"] == []


def test_the_form_sits_under_search_and_above_sort_by(site):
    site.sign_in()
    site.switch(places_enabled=True)
    html = site.client.get("/issues").text
    assert html.index('class="search"') < html.index('class="near"') < html.index("Sort by")
    assert '<label for="near-country">Near:</label>' in html and ">Show</button>" in html
    assert 'placeholder="Town or area, optional"' in html
    # Countries A to Z by name, after the empty first choice.
    names = re.findall(r'<option value="[A-Z]{2}"[^>]*>(.*?)</option>', html)
    assert len(names) == 249 and names[0] == "Afghanistan" and names[-1] == "Zimbabwe"


# Show (Q43).

def test_near_a_country_keeps_the_near_issues_with_whole_counts(site):
    site.sign_in()
    site.switch(places_enabled=True)
    full = site.client.get("/issues").text
    site.near_keys = {"rent", "berlin floods"}
    html = site.client.get("/issues?country=DE&area=").text
    assert site.asked["issues_near"] == [("DE", None)]
    assert "<h2>Issues near Germany</h2>" in html and '<a href="/issues">Show all issues</a>' in html
    # Flooding shows for its near sub-issue, with only that one under it; sorted as the full list.
    assert issue_names(html) == ["Flooding", "Rent"]
    assert "Floods in Berlin" in html and "Coastal floods" not in html
    # Counts are the whole record's: the same line as on the full list.
    line = re.search(r'Flooding</a></h2>\s*<p class="counts">(.*?)</p>', full).group(1)
    assert f'Flooding</a></h2>\n  <p class="counts">{line}</p>' in html and "3 claims in total" in line
    assert selected(html) == "DE"


def test_near_a_town_matches_its_key_and_the_sort_links_keep_it(site):
    site.sign_in()
    site.switch(places_enabled=True)
    site.near_keys = {"veto"}
    html = site.client.get("/issues?country=us&area=St.+Louis&sort=recent").text
    assert site.asked["issues_near"] == [("US", "st louis")]
    assert "<h2>Issues near St. Louis, United States</h2>" in html and issue_names(html) == ["Security Council veto"]
    assert 'href="/issues?sort=people&amp;country=US&amp;area=St.+Louis"' in html
    assert '<input type="hidden" name="sort" value="recent">' in html
    assert selected(html) == "US" and area_value(html) == "St. Louis"


def test_nothing_near_says_so(site):
    site.sign_in()
    site.switch(places_enabled=True)
    html = site.client.get("/issues?country=FR&area=Lyon").text
    assert ('<p class="empty">No statements have been placed in Lyon, France yet. '
            '<a href="/issues">Show all issues</a></p>') in html
    assert "No issues yet" not in html and issue_names(html) == []
    assert "Issues near" not in html and html.count("Show all issues") == 1


def test_a_town_without_a_country_asks_for_the_country(site):
    site.sign_in()
    site.switch(places_enabled=True)
    html = site.client.get("/issues?country=&area=Lyon").text
    assert '<p class="notice" role="alert">Please choose the country for this town or area.</p>' in html
    assert site.asked["issues_near"] == [] and len(issue_names(html)) == 3 and area_value(html) == "Lyon"


def test_an_empty_show_is_the_whole_list(site):
    site.sign_in()
    site.switch(places_enabled=True)
    site.last = {"country": "US", "area": None}
    html = site.client.get("/issues?country=&area=").text
    assert "Issues near" not in html and "Please choose" not in html and len(issue_names(html)) == 3
    assert site.asked["issues_near"] == [] and site.asked["last_place"] == [] and selected(html) == ""


def test_search_wins_over_near(site, monkeypatch):
    site.sign_in()
    site.switch(places_enabled=True)
    monkeypatch.setattr("app.search.run", lambda words, decorate: {"issues": [], "solutions": [], "evidence": [],
                                                                   "posts": []})
    html = site.client.get("/issues?q=veto&country=DE").text
    assert "Results for veto" in html and "Issues near" not in html and site.asked["issues_near"] == []


def test_the_log_line_has_counts_and_never_the_place(site, caplog):
    caplog.set_level(logging.DEBUG, logger="oci")
    site.sign_in()
    site.switch(places_enabled=True)
    site.near_keys = {"veto", "rent"}
    site.client.get("/issues?country=US&area=Springfield")
    lines = [json.loads(r.getMessage()) for r in caplog.records if '"event": "near"' in r.getMessage()]
    assert len(lines) == 1
    assert set(lines[0]) == {"event", "request_id", "by", "issues", "latency_ms"}
    assert lines[0]["by"] == "area" and lines[0]["issues"] == 2
    assert "Springfield" not in caplog.text
