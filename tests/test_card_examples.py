import json
from pathlib import Path

import pytest

from app.extract import Candidates, CardPayload, prepared_card, resolve_payload
from app.text import sentences

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "cards.json").read_text())


def test_drug_policy_sentences_match_the_six_acceptance_lines():
    assert sentences(CardPayload.model_validate(FIXTURES["1"]), "John Kintree") == [
        "John Kintree claims Drug dealing problem",
        "John Kintree proposes solution Decriminalize drug sales",
        "John Kintree proposes solution Treat drug use as medical issue",
        "Drug dealing problem has proposed Decriminalize drug sales",
        "Drug dealing problem has proposed Treat drug use as medical issue",
        "John Kintree approves Treat drug use as medical issue",
    ]


def test_seawall_sentences_match_the_five_acceptance_lines():
    assert sentences(CardPayload.model_validate(FIXTURES["4"]), "Tester") == [
        "Tester claims Rising sea levels threaten coastal housing",
        "Tester proposes solution Seawall in the harbor district",
        "Rising sea levels threaten coastal housing has proposed Seawall in the harbor district",
        "Tester submits evidence 2024 NOAA flooding survey",
        "2024 NOAA flooding survey supports issue of Rising sea levels threaten coastal housing",
    ]


def test_evidence_names_what_it_speaks_to_and_a_known_issue_is_claimed_about():
    """John, 23 October 2026: "supports solution of". John, 24 October 2026: an issue already in the
    record reads "claims about existing issue", whether or not the card adds anything else."""
    known = Candidates(issues={"flooding": {"name": "Flooding", "parent_key": None}}, evidence={"old report": "Old report"})
    card = CardPayload.model_validate({"found": True, "issues": [{"name": "Flooding"}, {"name": "Erosion"}],
                                       "solutions": [{"name": "Seawalls", "for_issue": "Flooding"}],
                                       "evidence": [{"name": "Survey", "about": "Seawalls", "stance": "supports"},
                                                    {"name": "Memo", "about": "Old report", "stance": "refutes"}]})
    assert sentences(card, "Ada", resolve_payload(card, known)) == [
        "Ada claims about existing issue Flooding", "Ada claims Erosion",
        "Ada proposes solution Seawalls", "Flooding has proposed Seawalls",
        "Ada submits evidence Survey", "Ada submits evidence Memo",
        "Survey supports solution of Seawalls", "Memo refutes evidence of Old report"]
    only = CardPayload.model_validate({"found": True, "issues": [{"name": "Flooding"}]})
    assert sentences(only, "Ada", resolve_payload(only, known)) == ["Ada claims about existing issue Flooding"]


def test_the_place_is_the_last_line_of_the_list():
    """John, 2 November 2026: he edited a post only to add St. Louis as its town, and the list said nothing
    about it. The place reads as it does under a post, after everything else; with none there is no line."""
    card = CardPayload.model_validate(FIXTURES["4"])
    assert sentences(card, "Tester", place="St. Louis, United States") == [
        *sentences(card, "Tester"), "Place: St. Louis, United States"]
    assert sentences(card, "Tester", place="Germany")[-1] == "Place: Germany"
    assert sentences(card, "Tester", place=None) == sentences(card, "Tester")


def test_a_solution_proposed_for_an_existing_issue_and_approved_is_one_line():
    """John, 2 November 2026 ("Wording"): adding a solution already in the database to an issue already in the
    database, with approval, gave four lines (claims about existing issue, proposes solution, has proposed,
    approves). He asked for one: "John Kintree proposes and approves solution of X for the issue of Y"."""
    known = Candidates(issues={"coastal flooding": {"name": "Coastal flooding", "parent_key": None},
                               "harbour dredging delays": {"name": "Harbour dredging delays", "parent_key": None}},
                       solutions={"seawalls": "Seawalls"}, solution_issues={"seawalls": ["Harbour dredging delays"]})

    def lines(card: dict) -> list[str]:
        payload = CardPayload.model_validate({"found": True, **card})
        return sentences(prepared_card(payload, known), "John Kintree", resolve_payload(payload, known))

    approved = {"name": "Seawalls", "for_issue": "Coastal flooding", "stance": "approve"}
    assert lines({"issues": [{"name": "Coastal flooding"}], "solutions": [approved]}) == [
        "John Kintree proposes and approves solution of Seawalls for the issue of Coastal flooding"]
    # The same with a new solution, or with the issue named only as the solution's issue.
    assert lines({"issues": [{"name": "Coastal flooding"}], "solutions": [{**approved, "name": "Dunes"}]}) == [
        "John Kintree proposes and approves solution of Dunes for the issue of Coastal flooding"]
    assert lines({"solutions": [approved]}) == [
        "John Kintree proposes and approves solution of Seawalls for the issue of Coastal flooding"]
    # Every other combination keeps its lines: no position, opposing, and a new issue (the acceptance lines above).
    assert lines({"issues": [{"name": "Coastal flooding"}], "solutions": [{**approved, "stance": "none"}]}) == [
        "John Kintree claims about existing issue Coastal flooding", "John Kintree proposes solution Seawalls",
        "Coastal flooding has proposed Seawalls"]
    assert lines({"issues": [{"name": "Coastal flooding"}], "solutions": [{**approved, "stance": "oppose"}]}) == [
        "John Kintree claims about existing issue Coastal flooding", "John Kintree proposes solution Seawalls",
        "Coastal flooding has proposed Seawalls", "John Kintree opposes Seawalls"]
    assert lines({"issues": [{"name": "Erosion"}], "solutions": [{**approved, "for_issue": "Erosion"}]}) == [
        "John Kintree claims Erosion", "John Kintree proposes solution Seawalls", "Erosion has proposed Seawalls",
        "John Kintree approves Seawalls"]
    # A solution already listed under the issue is a position only, as before (GitHub issue 4).
    assert lines({"issues": [{"name": "Harbour dredging delays"}],
                  "solutions": [{**approved, "for_issue": "Harbour dredging delays"}]}) == ["John Kintree approves Seawalls"]


@pytest.mark.parametrize("case", ["1", "4", "5", "6A", "7"])
def test_handwritten_card_fixtures_preserve_only_explicit_stances(case):
    card = CardPayload.model_validate(FIXTURES[case])
    resolved = resolve_payload(card, Candidates.empty())
    if case in ("5", "6A"):
        assert resolved.is_empty
    else:
        assert not resolved.dropped
        assert [item["stance"] for item in resolved.solutions] == (["none", "approve"] if case == "1" else ["none"])


def test_anonymous_sentences_contain_no_display_name():
    assert all("John" not in line for line in sentences(CardPayload.model_validate(FIXTURES["1"]), ""))


@pytest.mark.parametrize("case, stances", [("12", []), ("13", []), ("14", ["approve"]), ("15", []), ("16", ["approve"]), ("17", [])])
def test_session_5_fixtures_resolve_without_drops(case, stances):
    known = Candidates(issues={"global climate coordination": {"name": "Global climate coordination", "parent_key": None},
                               "data centers": {"name": "Data centers", "parent_key": None},
                               "democratic legitimacy of global institutions": {"name": "Democratic legitimacy of global institutions", "parent_key": None}},
                       solutions={"global carbon tax by referendum": "Global carbon tax by referendum",
                                  "platform for digital democracy": "Platform for digital democracy"},
                       solution_issues={"global carbon tax by referendum": ["Global climate coordination"],
                                        "platform for digital democracy": ["Democratic legitimacy of global institutions"]})
    resolved = resolve_payload(CardPayload.model_validate(FIXTURES[case]), known)
    assert not resolved.dropped
    assert [item["stance"] for item in resolved.solutions] == stances
    if case == "15":
        # John, 2 November 2026: the two "sub-issues" are reasons, read as evidence supporting Data centers.
        assert [row["key"] for row in resolved.issues] == ["data centers"]
        assert [(row["stance"], row["target_label"], row["target_key"]) for row in resolved.evidence] == [
            ("supports", "Issue", "data centers")] * 2
    if case == "16":
        assert [(row["target_label"], row["target_key"]) for row in resolved.evidence] == [("Solution", "more processing on personal devices")]
    if case == "17":
        assert [(row["target_label"], row["target_key"]) for row in resolved.evidence] == [("Solution", "platform for digital democracy")]


# 24 October 2026: the same link counts as the same evidence, whatever name the writer typed.
LINKED = Candidates(
    issues={"flooding": {"name": "Flooding", "parent_key": None}},
    evidence={"old report": "Old report", "other report": "Other report", "reuters com world": "reuters.com/world"},
    evidence_links={"example.org/report": "old report", "example.org/other": "other report",
                    "reuters.com/world": "reuters com world"},
)


def _evidence(name, url):
    payload = CardPayload.model_validate({"issues": [{"name": "Flooding"}],
                                          "evidence": [{"name": name, "url": url, "about": "Flooding"}]})
    return resolve_payload(payload, LINKED).evidence[0]


def test_same_link_under_a_different_name_joins_the_existing_evidence():
    row = _evidence("Flood study 2024", "https://example.org/report")
    assert (row["key"], row["name"], row["existing"]) == ("old report", "Old report", True)
    card = CardPayload.model_validate({"issues": [{"name": "Flooding"}],
                                       "evidence": [{"name": "Flood study 2024", "url": "https://example.org/report", "about": "Flooding"}]})
    shown = prepared_card(card, LINKED)  # what the card gets back, as /api/preview builds it
    assert shown.evidence[0].name == "Old report"
    assert sentences(shown, "Pat", resolve_payload(shown, LINKED)) == [
        "Pat claims about existing issue Flooding", "Pat submits evidence Old report", "Old report supports issue of Flooding"]


@pytest.mark.parametrize("url", [
    "http://example.org/report", "https://www.example.org/report", "https://example.org/report/",
    "https://example.org/report?utm_source=mail&utm_medium=x", "https://example.org/report#section-2",
    "HTTPS://EXAMPLE.ORG/report",
])
def test_scheme_www_trailing_slash_utm_and_fragment_do_not_make_a_new_piece_of_evidence(url):
    assert _evidence("Flood study 2024", url)["key"] == "old report"


def test_a_different_query_is_a_different_piece_of_evidence():
    row = _evidence("Flood study 2024", "https://example.org/report?page=2")
    assert (row["key"], row["existing"]) == ("flood study 2024", False)


def test_a_name_already_in_the_record_wins_over_the_link():
    row = _evidence("Other report", "https://example.org/report")
    assert (row["key"], row["name"]) == ("other report", "Other report")


def test_evidence_named_only_by_its_link_still_joins():
    row = _evidence("", "http://www.reuters.com/world/")
    assert (row["key"], row["name"], row["existing"]) == ("reuters com world", "reuters.com/world", True)


def test_a_card_posted_alone_names_a_link_only_piece_of_evidence_once():
    # John, 31 October 2026: with no statement written, the card's lines become the statement, and a link
    # with no words beside it showed twice in it ("submits evidence <link>", then "<link> refutes ...").
    url = "https://www.aei.org/commentary/data-centers-make-easy-targets/?gad_source=1&gad_campaignid=9"
    card = CardPayload.model_validate({"issues": [{"name": "Data centers problem"}], "evidence": [
        {"name": "", "url": url, "stance": "refutes", "about": "Data centers problem"}]})
    shown = prepared_card(card, Candidates.empty())
    lines = sentences(shown, "John Kintree", resolve_payload(shown, Candidates.empty()))
    assert lines == ["John Kintree claims Data centers problem",
                     "John Kintree submits evidence Aei.org/commentary/data-centers-make-easy-targets, "
                     "which refutes issue of Data centers problem"]
    assert ". ".join(lines).lower().count("aei.org") == 1


def test_a_link_with_a_name_of_its_own_keeps_its_two_lines():
    card = CardPayload.model_validate({"issues": [{"name": "Flooding"}], "evidence": [
        {"name": "Flood study 2024", "url": "https://example.org/new", "about": "Flooding"}]})
    assert sentences(card, "Pat")[-2:] == ["Pat submits evidence Flood study 2024",
                                           "Flood study 2024 supports issue of Flooding"]


def test_a_short_typed_name_with_a_known_link_is_kept_not_dropped():
    assert _evidence("ab", "https://example.org/report")["key"] == "old report"


def test_evidence_can_be_about_evidence_matched_by_link():
    payload = CardPayload.model_validate({"issues": [{"name": "Flooding"}], "evidence": [
        {"name": "Flood study 2024", "url": "https://example.org/report", "about": "Flooding"},
        {"name": "A rebuttal", "url": "https://example.org/rebuttal", "stance": "refutes", "about": "Old report"}]})
    rows = resolve_payload(payload, LINKED).evidence
    assert [(r["target_label"], r["target_key"]) for r in rows] == [("Issue", "flooding"), ("Evidence", "old report")]


@pytest.mark.parametrize("url, expected", [
    ("https://www.youtube.com/watch?v=abc&utm_source=x", "youtube.com/watch?v=abc"),
    ("https://www.aei.org/commentary/x/?gad_source=1&gad_campaignid=2&gclid=abc", "aei.org/commentary/x"),
    ("https://example.org/a?fbclid=1&page=2&msclkid=3", "example.org/a?page=2"),
    ("http://Example.org/", "example.org"),
    ("https://arxiv.org/abs/1234.5678", "arxiv.org/abs/1234.5678"),
    ("https://arxiv.org/pdf/1234.5678", "arxiv.org/pdf/1234.5678"),
    (None, ""),
])
def test_link_key(url, expected):
    from app.payload import link_key

    assert link_key(url) == expected
