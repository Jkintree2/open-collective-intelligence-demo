"""Phase 3, ask the record: the digest built from rows (ask.build, ask.pick_issues). No database."""

import json
from datetime import date, datetime, timezone

import pytest

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
            "stances": [{"stance": s, "date": f"2026-10-{d:02d}", "post_ids": ids, "click": not ids}
                        for s, d, ids in stances]}


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
    assert list(digest) == ["asked_about", "issues", "solutions", "evidence", "evidence_backed_by_other_evidence",
                            "posts"]
    assert digest["evidence_backed_by_other_evidence"] == 0
    assert digest["asked_about"] == "the issue Climate"
    assert digest["issues"] == [{"name": "Climate", "part_of": "World government", "sub_issues": ["Carbon prices"],
                                 "people_claiming": 4}]
    assert digest["solutions"][0] == {"id": "S1", "name": "Tax", "issues": ["Climate"], "approved_by": 2,
                                      "opposed_by": 1, "proposed_by": 1}


def test_a_click_and_a_post_not_read_are_told_apart():
    """The walk of 26 October: a stance whose post was not read looked like a click."""
    sols = [solution("veto", [("oppose", 5, ["unread"]), ("approve", 4, []), ("approve", 3, ["read"])], 2, 1)]
    _, digest = digest_of(None, [ISSUE], sols, [], [(post("read", 3), "climate")])
    assert digest["solutions"][0]["stances"] == [
        {"stance": "oppose", "date": "2026-10-05", "post_not_read": True},
        {"stance": "approve", "date": "2026-10-04", "click": True},
        {"stance": "approve", "date": "2026-10-03", "posts": ["P1"]}]


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
    _, digest = digest_of("Climate", [ISSUE], [], [], posts, cap=empty + 500)
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
    assert source.text == long_text[:200].rstrip() + "\u2026" and source.when == "3 October 2026"
    assert built.sources["S1"].href == "/issues/climate" and built.sources["S1"].name == "Tax"
    assert built.sources["E1"].kind == "evidence" and built.sources["E1"].href == "/issues/climate"
    assert json.loads(built.text)["posts"][0]["edited"] == "2026-10-07"
    # John, 30 October: a kept answer is shown only while the posts it cites are as they were, so a post
    # source knows its post; nothing else has one.
    assert (source.post_id, built.sources["S1"].post_id, built.sources["E1"].post_id) == ("a", None, None)


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
    assert dashboard["about"] == [{"what": "issue Climate", "side": "supports", "page_read_as": "agrees", "post": "P1"}]
    assert dashboard["supported_by"] == ["E3"] and dashboard["refuted_by"] == ["E4"]
    assert digest["evidence_backed_by_other_evidence"] == 1
    assert pieces["Study"]["about"] == [{"what": "solution S1", "side": "refutes", "page_read_as": "partly agrees",
                                         "post": "P2"}]
    assert pieces["Imf"]["about"] == [{"what": "evidence E1", "side": "supports", "post": "P2"}]
    assert pieces["Plant"]["about"] == [{"what": "solution Elsewhere", "side": "supports",
                                         "from_personal_experience": True}]


def test_at_most_thirty_pieces_of_evidence_and_nothing_points_past_them():
    rows = [edge(f"piece{n:02d}", "issue", "climate") for n in range(1, 35)]
    rows.append(edge("piece01", "evidence", "piece33"))  # into a piece past the cap
    _, digest = digest_of("Climate", [ISSUE], [], rows, [])
    assert [item["name"] for item in digest["evidence"]] == [f"Piece{n:02d}" for n in range(1, 31)]
    assert all(len(item["about"]) == 1 for item in digest["evidence"])
    assert "E31" not in json.dumps(digest)


def test_each_piece_of_evidence_links_to_its_own_issue_on_the_whole_record():
    rows = [edge("report", "issue", "veto", target_name="Security Council veto"),
            edge("study", "solution", "tax"), edge("note", "evidence", "report"), edge("loose", "solution", "other")]
    built, _ = digest_of(None, [ISSUE], [solution("tax", [], 1)], rows, [])
    found = {s.name: (s.href, s.issue) for s in built.sources.values() if s.kind == "evidence"}
    assert found == {"Report": ("/issues/veto", "Security Council veto"), "Study": ("/issues/climate", "Climate"),
                     "Note": (None, None), "Loose": (None, None)}


HOMELESSNESS = {"key": "homelessness", "name": "Homelessness", "people": 2, "claims": 2}


def two_issue_solution(stances: list[tuple[str, int, list[str]]] = ()):
    row = solution("shelter", list(stances), 3)
    row["issues"] = [{"key": "world government", "name": "World government"},
                     {"key": "homelessness", "name": "Homelessness"}]
    return row


def test_a_solution_under_two_issues_is_shown_on_the_one_the_question_is_about():
    """John, 3 November: a solution under two issues was shown "On" the first of them, not the one asked about."""
    built, _ = digest_of(None, [HOMELESSNESS], [two_issue_solution()], [edge("study", "solution", "shelter")], [])
    assert (built.sources["S1"].issue, built.sources["S1"].href) == ("Homelessness", "/issues/homelessness")
    assert (built.sources["E1"].issue, built.sources["E1"].href) == ("Homelessness", "/issues/homelessness")
    # None of its issues asked about: it keeps its first.
    built, _ = digest_of(None, [ISSUE], [two_issue_solution()], [], [])
    assert built.sources["S1"].issue == "World government"


def test_a_post_behind_a_top_solution_is_shown_on_the_issue_the_question_is_about(monkeypatch):
    issues = {"homelessness": "Homelessness", "world government": "World government"}
    monkeypatch.setattr(ask.graph_search, "search_posts", lambda query: [])
    monkeypatch.setattr(ask.graph_search, "search_names", lambda query: [
        {"label": "Issue", "key": "homelessness", "solution_homes": [], "evidence_homes": []}])
    monkeypatch.setattr(ask.graph, "post_structure", lambda ids: {})
    monkeypatch.setattr(ask.graph, "issue_header", lambda key: {"key": key, "name": issues[key], "children": []})
    monkeypatch.setattr(ask.graph, "issue_claimants", lambda key: {"people": 1, "claims": 1})
    monkeypatch.setattr(ask.graph, "issue_posts", lambda key, limit: [])
    monkeypatch.setattr(ask.graph_own_posts, "post_flags", lambda who, ids: {})
    for name in ("issue_stances", "issue_evidence"):
        monkeypatch.setattr(ask.graph_ask, name, lambda key: [])
    monkeypatch.setattr(ask.graph_ask, "top_solutions", lambda limit: [two_issue_solution([("approves", 2, ["p9"])])])
    for name in ("top_opposed", "top_evidence"):
        monkeypatch.setattr(ask.graph_ask, name, lambda limit: [])
    monkeypatch.setattr(ask.graph_ask, "posts_by_ids", lambda ids: [post("p9", 2)])
    built = ask.record_digest("How does homelessness relate to the UDHR?")
    assert (built.sources["P1"].issue, built.sources["P1"].href) == ("Homelessness", "/issues/homelessness")
    assert built.sources["S1"].issue == "Homelessness"


def test_a_digest_knows_the_posts_that_cited_each_piece_of_evidence():
    rows = [edge("report", "issue", "climate", post_id="a"), edge("report", "solution", "tax", post_id="b"),
            edge("study", "issue", "climate", post_id="gone"), edge("note", "evidence", "report")]
    built, _ = digest_of("Climate", [ISSUE], [solution("tax", [], 1)], rows, [(post("a", 3), "climate"),
                                                                             (post("b", 2), "climate")])
    # A post not in the digest is never named; a piece no post cited has none.
    assert built.evidence_posts == {"E1": ["P1", "P2"], "E2": [], "E3": []}
    # A piece only spoken to by other evidence has no "about" of its own.
    built, _ = digest_of("Climate", [ISSUE], [], [edge("note", "evidence", "report", post_id="a")],
                         [(post("a", 3), "climate")])
    assert built.evidence_posts == {"E1": ["P1"], "E2": []}


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


def test_a_whole_record_question_looks_for_its_topic_not_the_documents_it_names(monkeypatch):
    """John, 29 October: the names and the posts that pick the issues are both found with ask.issue_query. John,
    3 November: then the solutions named after the document it names are looked for, picking no issue."""
    searched = []
    monkeypatch.setattr(ask.graph_search, "search_posts", lambda query: searched.append(query) or [])
    monkeypatch.setattr(ask.graph_search, "search_names", lambda query: searched.append(query) or [])
    monkeypatch.setattr(ask.graph, "post_structure", lambda ids: {})
    for name in ("top_solutions", "top_opposed", "top_evidence"):
        monkeypatch.setattr(ask.graph_ask, name, lambda limit: [])
    monkeypatch.setattr(ask.graph_ask, "posts_by_ids", lambda ids: [])
    ask.record_digest("How does climate change relate to the Earth Charter?")
    assert searched == ["(climate climate*) (change change*) (relate relate*)"] * 2 + ['"earth charter"']


A25 = "Use money from global carbon tax to realize Article 25 of the UDHR"


def crowded(monkeypatch, read: list[list[str]]):
    """A record whose top ten solutions hold four unread stance posts each, and a solution named after the UDHR,
    proposed in one post and approved in another. `read` gets each list of post ids asked for."""
    monkeypatch.setattr(ask.graph_search, "search_posts", lambda query: [])
    monkeypatch.setattr(ask.graph_search, "search_names", lambda query: [
        {"label": "Solution", "key": "a25", "name": A25, "score": 0.7}] if "udhr" in query else [])
    monkeypatch.setattr(ask.graph, "post_structure", lambda ids: {})
    top = [solution(f"top {n}", [("approve", 2, [f"t{n}-{m}"]) for m in range(4)], approves=4) for n in range(10)]
    for row in top:
        row["issues"] = []
    monkeypatch.setattr(ask.graph_ask, "top_solutions", lambda limit: top)
    for name in ("top_opposed", "top_evidence"):
        monkeypatch.setattr(ask.graph_ask, name, lambda limit: [])
    named = dict(solution("a25", [("approve", 1, ["a25-stance"])], approves=1, proposed_in=["a25-proposal"]),
                 name=A25)
    monkeypatch.setattr(ask.graph_ask, "solution_stances", lambda key: [named] if key == "a25" else [])
    monkeypatch.setattr(ask.graph_ask, "posts_by_ids", lambda ids: read.append(ids) or [])


def test_the_posts_behind_a_solution_named_after_the_document_are_read_before_the_cap(monkeypatch):
    """Review, 3 November: added after the top solutions, its stance posts came last and the 40 cut them; the
    post that proposed it without a stance was never asked for."""
    read: list[list[str]] = []
    crowded(monkeypatch, read)
    ask.record_digest("How does homelessness relate to the principles of the UDHR?")
    assert {"a25-proposal", "a25-stance"} <= set(read[0]) and len(read[0]) == ask.RECORD_STANCE_POSTS


HOMELESSNESS_UDHR = "How does homelessness relate to the principles of the UDHR?"


@pytest.mark.parametrize("follow_up", ["Tell me more", "Tell me more.", "List them all", "In detail, please",
                                       "Tell me more in detail", "Can you say more?"])
def test_a_question_that_only_asks_for_more_is_looked_up_by_the_question_before_it(follow_up):
    """John, 3 November: "Tell me more" has no words of its own to look up, so after his homelessness question
    it read the top solutions alone, and neither homelessness nor the solution naming Article 25."""
    assert ask.lookup_question(follow_up, [HOMELESSNESS_UDHR]) == HOMELESSNESS_UDHR


def test_a_second_tell_me_more_still_reaches_the_question_with_words():
    assert ask.lookup_question("Tell me more", ["Why?", HOMELESSNESS_UDHR, "Tell me more"]) == HOMELESSNESS_UDHR


@pytest.mark.parametrize("question, earlier", [
    ("Tell me more about the carbon tax", [HOMELESSNESS_UDHR]),  # words of its own
    ("Tell me more about the principles", ["What about the veto?"]),
    ("Tell me more", []),
    ("Tell me more", ["Why?"]),
    # Only the earlier questions the answer is given: the oldest of four is left out of both.
    ("Tell me more", [HOMELESSNESS_UDHR, "Why?", "Why not?", "And?"])])
def test_a_question_keeps_its_own_lookup_otherwise(question, earlier):
    assert ask.lookup_question(question, earlier) == question


def test_a_name_citing_an_article_comes_before_shorter_names_that_only_name_the_document(monkeypatch):
    """Review, 3 November: Q26 scores a long name low, so five short names holding "UDHR" pushed out the one
    John asked about."""
    rows = [{"label": "Solution", "key": f"short {n}", "name": f"UDHR plan {n}", "score": 2.5} for n in range(6)]
    rows.append({"label": "Solution", "key": "a25", "name": A25, "score": 0.7})
    monkeypatch.setattr(ask.graph_search, "search_names", lambda query: rows)
    monkeypatch.setattr(ask.graph_ask, "solution_stances", lambda key: [{"key": key}])
    keys = [row["key"] for row in ask.document_solutions("How does homelessness relate to the principles of the UDHR?")]
    assert keys[0] == "a25" and len(keys) == ask.DOCUMENT_SOLUTIONS


# QA of v0.3, 8 November: a question with no words of its own is answered but never kept or listed (routes_ask, home_lists).
@pytest.mark.parametrize("question, own", [("Tell me more", False), ("Tell me more.", False), ("Why?", False),
                                           ("List them all", False), ("In detail, please", False),
                                           ("Who pays?", True), ("Is it fair?", True), (HOMELESSNESS_UDHR, True),
                                           ("Tell me more about the carbon tax", True), ("What does the UDHR say?", True)])
def test_a_question_has_words_of_its_own_or_only_follows_another(question, own):
    assert ask.has_own_words(question) is own


# John, 11 November 2026 ("Asking"): asked whether anyone had said anything about abortion, Ask answered that the
# database says nothing yet. The issue the question's words found was read, but its one post, older than the posts
# of the two issues filled in from the top solutions, was cut by the cap; and a post that named the topic but was
# posted without an issue was never read at all.

def test_posts_the_question_found_lead_the_digest():
    posts = [(post("old-other", 1), "climate"), (post("new-other", 9), "climate"), (post("new-stance", 5), "climate")]
    sols = [solution("tax", [("approve", 5, ["new-stance"])], 1)]
    _, digest = digest_of(None, [ISSUE], sols, [], posts, lead=["old-other"])
    assert [p["text"] for p in digest["posts"]] == ["Post old-other.", "Post new-stance.", "Post new-other."]
    # Inside the lead, stance posts still come first, then the newest.
    _, digest = digest_of(None, [ISSUE], sols, [], posts, lead=["old-other", "new-stance"])
    assert [p["text"] for p in digest["posts"]] == ["Post new-stance.", "Post old-other.", "Post new-other."]


def abortion_record(monkeypatch, found_posts: list[dict]):
    """One small issue the question's words find, holding one long post from 3 November and one piece of evidence
    it cited; two filler issues, from the top solutions, with many newer posts and stances. `found_posts` is what
    the post search returns."""
    issues = {"abortion rights": "Abortion rights", "climate": "Climate", "platform": "Platform"}
    roe = post("roe", 3, "The Supreme Court ruled on abortion in Roe v Wade. " * 12, name="John Kintree")
    roe["created_at"] = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)
    newer = {key: [dict(post(f"{key}-{n}", 9, f"{key} post {n} " * 40, name="Ada Okafor"),
                        created_at=datetime(2026, 11, 10, 9, n, tzinfo=timezone.utc)) for n in range(40)]
             for key in ("climate", "platform")}
    by_issue = {"abortion rights": [roe], **newer}
    top = []
    for key in ("climate", "platform"):
        for n in range(5):
            row = solution(f"{key} solution {n}", [("approve", 9, [f"{key}-s{n}-{m}"]) for m in range(4)], 4)
            row["issues"] = [{"key": key, "name": issues[key]}]
            top.append(row)
    monkeypatch.setattr(ask.graph_search, "search_names", lambda query: [
        {"label": "Issue", "key": "abortion rights", "name": "Abortion rights", "solution_homes": [],
         "evidence_homes": []}])
    monkeypatch.setattr(ask.graph_search, "search_posts", lambda query: [dict(row) for row in found_posts])
    monkeypatch.setattr(ask.graph, "post_structure", lambda ids: {
        pid: [{"rel": "CLAIM", "to_key": "abortion rights"}] for pid in ids if pid == "roe"})
    monkeypatch.setattr(ask.graph, "issue_header", lambda key: {"key": key, "name": issues[key], "children": []})
    monkeypatch.setattr(ask.graph, "issue_claimants", lambda key: {"people": 1, "claims": 1})
    monkeypatch.setattr(ask.graph, "issue_posts", lambda key, limit: [dict(p) for p in by_issue[key]])
    monkeypatch.setattr(ask.graph_own_posts, "post_flags", lambda who, ids: {})
    monkeypatch.setattr(ask.graph_ask, "issue_stances", lambda key: [r for r in top if r["issues"][0]["key"] == key])
    monkeypatch.setattr(ask.graph_ask, "issue_evidence", lambda key: [
        edge("roe evidence", "issue", "abortion rights", post_id="roe")] if key == "abortion rights" else [
        edge(f"{key} evidence {n}", "issue", key, post_id=f"{key}-{n}") for n in range(12)])
    monkeypatch.setattr(ask.graph_ask, "top_solutions", lambda limit: top[:limit])
    for name in ("top_opposed", "top_evidence"):
        monkeypatch.setattr(ask.graph_ask, name, lambda limit: [])
    monkeypatch.setattr(ask.graph_ask, "posts_by_ids", lambda ids: [
        post(pid, 10, "A reason for this stance, written out at some length. " * 4) for pid in ids])
    return roe


def test_a_whole_record_question_reads_the_found_issues_posts_before_the_cap(monkeypatch):
    abortion_record(monkeypatch, [])
    built = ask.record_digest("Has anyone said anything about abortion?")
    assert built.posts_left_out > 0  # the record is over the cap, as the live one was
    roe = next((sid for sid, source in built.sources.items() if source.post_id == "roe"), None)
    assert roe is not None and built.sources[roe].issue == "Abortion rights"
    evidence = next(sid for sid, source in built.sources.items() if source.name == "Roe Evidence")
    assert built.evidence_posts[evidence] == [roe]


def test_a_post_found_by_its_words_is_read_though_linked_to_nothing(monkeypatch):
    unlinked = dict(post("unlinked", 11, "Abortion should be legal.", name=None, anonymous=True), edited_at=None)
    others = [dict(post(f"bare-{n}", 10, f"Abortion, said again {n}.", name="Ada Okafor"), edited_at=None)
              for n in range(6)]
    roe = abortion_record(monkeypatch, [unlinked, dict(post("roe", 3, "Roe."), edited_at=None)] + others)
    built = ask.record_digest("Has anyone said anything about abortion?")
    read = {source.post_id: source for source in built.sources.values() if source.kind == "post"}
    assert (read["unlinked"].name, read["unlinked"].href, read["unlinked"].issue) == ("Anonymous", None, None)
    # The post search's first five, in its order; one already read under its issue is not read twice.
    assert "roe" in read and read["roe"].text.startswith(roe["text"][:40])
    assert {"bare-0", "bare-1", "bare-2"} <= set(read) and not {"bare-3", "bare-4", "bare-5"} & set(read)
    assert len([pid for pid in read if pid in ("unlinked", "roe")]) == 2
