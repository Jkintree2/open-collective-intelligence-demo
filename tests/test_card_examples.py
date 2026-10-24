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
        assert [item["parent_key"] for item in resolved.issues] == [None, "data centers", "data centers"]
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
    ("http://Example.org/", "example.org"),
    ("https://arxiv.org/abs/1234.5678", "arxiv.org/abs/1234.5678"),
    ("https://arxiv.org/pdf/1234.5678", "arxiv.org/pdf/1234.5678"),
    (None, ""),
])
def test_link_key(url, expected):
    from app.payload import link_key

    assert link_key(url) == expected
