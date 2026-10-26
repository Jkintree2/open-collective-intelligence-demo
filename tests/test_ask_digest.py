"""Phase 3, ask the record: the digest built from rows (ask.build, ask.pick_issues). No database."""

import json
from datetime import date, datetime, timezone

from app import ask

ISSUE = {"key": "climate", "name": "Climate", "parent": "World government", "sub_issues": ["Carbon prices"],
         "people": 4, "claims": 5}


def at(day: int) -> datetime:
    return datetime(2026, 10, day, 9, 0, tzinfo=timezone.utc)


def post(pid: str, day: int, text: str = "", name: str | None = "Ada Okafor", anonymous: bool = False, **extra):
    return {"id": pid, "text": text or f"Post {pid}.", "display_name": name, "anonymous": anonymous,
            "created_at": at(day), "seed": False, **extra}


def solution(key: str, stances: list[tuple[str, int, list[str]]], approves: int = 0, opposes: int = 0,
             proposed_in: list[str] | None = None):
    return {"key": key, "name": key.title(), "issues": [{"key": "climate", "name": "Climate"}], "proposers": 1,
            "proposed_in": proposed_in or [], "approves": approves, "opposes": opposes,
            "stances": [{"stance": s, "date": f"2026-10-{d:02d}", "post_ids": ids} for s, d, ids in stances]}


def edge(key: str, target_kind: str, target_key: str, stance: str = "supports", **extra):
    return {"key": key, "name": key.title(), "url": f"https://example.org/{key}", "source_known": False,
            "target_kind": target_kind, "target_key": target_key, "target_name": target_key.title(),
            "target_url": None, "stance": stance, "check": None, "personal": None, "post_id": None,
            "created_at": at(1), **extra}


def digest_of(*args, **kwargs):
    built = ask.build(*args, **kwargs)
    return built, json.loads(built.text)


def test_posts_that_took_a_stance_come_first_then_the_rest_each_newest_first():
    posts = [(post("old-stance", 1), "climate"), (post("new-other", 9), "climate"),
             (post("new-stance", 5), "climate"), (post("old-other", 2), "climate")]
    sols = [solution("tax", [("oppose", 5, ["new-stance"]), ("approve", 1, ["old-stance"])], 1, 1)]
    built, digest = digest_of("Climate", [ISSUE], sols, [], posts)
    assert [p["text"] for p in digest["posts"]] == ["Post new-stance.", "Post old-stance.", "Post new-other.",
                                                    "Post old-other."]
    assert [p["id"] for p in digest["posts"]] == ["P1", "P2", "P3", "P4"]
    assert digest["solutions"][0]["stances"] == [{"stance": "oppose", "date": "2026-10-05", "posts": ["P1"]},
                                                 {"stance": "approve", "date": "2026-10-01", "posts": ["P2"]}]
    assert "note" not in digest and built.posts_left_out == 0 and built.posts_in == 4


def test_the_head_comes_first_in_the_plans_order():
    sols = [solution("tax", [], 2, 1)]
    _, digest = digest_of("Climate", [ISSUE], sols, [edge("report", "issue", "climate")], [(post("a", 1), "climate")])
    assert list(digest) == ["asked_about", "issues", "solutions", "evidence", "posts"]
    assert digest["asked_about"] == "the issue Climate"
    assert digest["issues"] == [{"name": "Climate", "part_of": "World government", "sub_issues": ["Carbon prices"],
                                 "people_claiming": 4}]
    assert digest["solutions"][0] == {"id": "S1", "name": "Tax", "issues": ["Climate"], "approved_by": 2,
                                      "opposed_by": 1, "proposed_by": 1}


def test_a_post_read_under_two_issues_is_listed_once():
    shared = post("shared", 3)
    _, digest = digest_of(None, [ISSUE, {**ISSUE, "key": "veto", "name": "Veto"}], [], [],
                          [(shared, "climate"), (dict(shared), "veto"), (post("b", 1), "veto")])
    assert [p["text"] for p in digest["posts"]] == ["Post shared.", "Post b."]
    assert digest["asked_about"] == "the whole record"


def test_a_solution_found_twice_keeps_its_first_place():
    rows = [solution("tax", [], 3), solution("fee", [], 2), solution("tax", [], 3)]
    _, digest = digest_of(None, [ISSUE], rows, [], [])
    assert [(s["id"], s["name"]) for s in digest["solutions"]] == [("S1", "Tax"), ("S2", "Fee")]


def test_posts_that_do_not_fit_are_counted_and_never_cited():
    long_text = "x" * 400
    posts = [(post(f"p{n}", n, long_text), "climate") for n in range(1, 11)]
    sols = [solution("tax", [("approve", n, [f"p{n}"]) for n in range(10, 0, -1)], 10)]
    built, digest = digest_of("Climate", [ISSUE], sols, [], posts, cap=2500)
    assert built.chars <= 2500
    kept = len(digest["posts"])
    assert 0 < kept < 10 and built.posts_left_out == 10 - kept
    assert digest["note"] == f"{10 - kept} more posts were left out."
    cited = {pid for stance in digest["solutions"][0]["stances"] for pid in stance.get("posts", [])}
    assert cited == {p["id"] for p in digest["posts"]}
    assert set(built.sources) == cited | {"S1"}


def test_one_post_left_out_is_said_in_the_singular():
    posts = [(post("a", 2, "y" * 300), "climate"), (post("b", 1, "y" * 300), "climate")]
    empty = len(ask.build("Climate", [ISSUE], [], [], []).text)
    _, digest = digest_of("Climate", [ISSUE], [], [], posts, cap=empty + 450)
    assert digest["note"] == "1 more post was left out."


def test_an_anonymous_post_never_carries_a_name():
    posts = [(post("a", 1, "My reason.", name="Secret Writer", anonymous=True), "climate"),
             (post("b", 2, "Mine.", name=None, anonymous=False), "climate")]
    built, digest = digest_of("Climate", [ISSUE], [], [], posts)
    assert "Secret Writer" not in built.text
    assert [p["by"] for p in digest["posts"]] == ["Anonymous", "Anonymous"]
    assert built.sources["P2"].name == "Anonymous"


def test_sources_hold_what_the_page_shows():
    long_text = "word " * 100
    sols = [solution("tax", [], 1)]
    built, _ = digest_of("Climate", [ISSUE], sols, [edge("report", "issue", "climate")],
                         [(post("a", 3, long_text, edited_at=at(7)), "climate sub")])
    source = built.sources["P1"]
    assert (source.kind, source.name, source.date, source.href) == ("post", "Ada Okafor", "2026-10-03",
                                                                     "/issues/climate%20sub")
    assert source.text == long_text[:200]
    assert built.sources["S1"].href == "/issues/climate" and built.sources["S1"].name == "Tax"
    assert built.sources["E1"].kind == "evidence" and built.sources["E1"].href == "/issues/climate"
    assert json.loads(built.text)["posts"][0]["edited"] == "2026-10-07"


def test_evidence_carries_its_reading_its_source_and_evidence_on_evidence():
    rows = [
        edge("dashboard", "issue", "climate", check="supports", post_id="a", source_known=True,
             source_type="organisation", source_primary=True, source_published="2023-11", source_cites=True),
        edge("study", "solution", "tax", stance="refutes", check="partly", post_id="b"),
        edge("imf", "evidence", "dashboard", check="unclear", post_id="b"),
        edge("oecd", "evidence", "dashboard", stance="refutes"),
        edge("plant", "solution", "elsewhere", personal=True),
    ]
    sols = [solution("tax", [], 1)]
    _, digest = digest_of("Climate", [ISSUE], sols, rows, [(post("a", 2), "climate"), (post("b", 1), "climate")],
                          today=date(2026, 10, 26))
    pieces = {item["name"]: item for item in digest["evidence"]}
    assert [item["id"] for item in digest["evidence"]] == ["E1", "E2", "E3", "E4", "E5"]
    dashboard = pieces["Dashboard"]
    assert dashboard["link"] == "https://example.org/dashboard"
    assert dashboard["source"] == "An organisation's page from November 2023. Primary source. Names its sources."
    assert dashboard["about"] == [{"what": "issue Climate", "says": "supports", "page_read_as": "agrees", "post": "P1"}]
    assert dashboard["supported_by"] == ["E3"] and dashboard["refuted_by"] == ["E4"]
    assert pieces["Study"]["about"] == [{"what": "solution S1", "says": "refutes", "page_read_as": "partly agrees",
                                         "post": "P2"}]
    assert pieces["Imf"]["about"] == [{"what": "evidence E1", "says": "supports", "post": "P2"}]
    assert pieces["Plant"]["about"] == [{"what": "solution Elsewhere", "says": "supports",
                                         "from_personal_experience": True}]


def test_at_most_thirty_pieces_of_evidence_and_nothing_points_past_them():
    rows = [edge(f"piece{n:02d}", "issue", "climate") for n in range(1, 35)]
    rows.append(edge("piece01", "evidence", "piece33"))  # into a piece past the cap
    _, digest = digest_of("Climate", [ISSUE], [], rows, [])
    assert [item["name"] for item in digest["evidence"]] == [f"Piece{n:02d}" for n in range(1, 31)]
    assert all(len(item["about"]) == 1 for item in digest["evidence"])
    assert "E31" not in json.dumps(digest)


def test_nothing_in_the_record_still_makes_a_digest():
    built, digest = digest_of("Climate", [ISSUE], [], [], [])
    assert digest == {"asked_about": "the issue Climate", "issues": [ISSUE_ENTRY]} and built.sources == {}


ISSUE_ENTRY = {"name": "Climate", "part_of": "World government", "sub_issues": ["Carbon prices"], "people_claiming": 4}


def test_whole_record_issues_are_picked_by_rank_in_names_and_posts():
    names = [{"label": "Solution", "key": "tax", "solution_homes": ["climate"], "evidence_homes": []},
             {"label": "Issue", "key": "veto", "solution_homes": [], "evidence_homes": []},
             {"label": "Evidence", "key": "report", "solution_homes": [], "evidence_homes": ["climate", "climate"]},
             {"label": "Evidence", "key": "loose", "solution_homes": [], "evidence_homes": []}]
    posts = [{"id": "p1"}, {"id": "p2"}]
    structure = {"p1": [{"rel": "CLAIM", "to_key": "housing"}, {"rel": "PROPOSE", "to_key": "tax"}],
                 "p2": [{"rel": "CLAIM", "to_key": "veto"}, {"rel": "CLAIM", "to_key": "flooding"}]}
    # Names first in score order (their issues), then the issues the posts claim; no repeats.
    assert ask.pick_issues(names, posts, structure) == ["climate", "veto", "housing"]
    assert ask.pick_issues(names, posts, structure, limit=5) == ["climate", "veto", "housing", "flooding"]
    assert ask.pick_issues(names[3:], posts, structure) == ["housing", "veto", "flooding"]
    assert ask.pick_issues([], [], {}) == []
