import json
from pathlib import Path

import pytest

from scripts.case_checks import failures, validate

VETO = "Limit or abolish the Security Council veto"


def card(issues=(), solutions=(), evidence=(), found=True, language_ok=True):
    return {"language_ok": language_ok, "found": found, "note": "",
            "issues": [{"name": name, "existing": existing} for name, existing in issues],
            "solutions": [{"name": name, "for_issue": for_issue, "stance": stance, "stance_only": False}
                          for name, for_issue, stance in solutions],
            "evidence": [{"name": name, "url": url, "stance": stance, "about": about}
                         for name, url, stance, about in evidence]}


DATA_CENTERS = card(issues=[("Data centers", True)],
                    evidence=[("Data centers raise electricity prices", None, "supports", "Data centers")])


def test_found_and_language_ok_compare_the_flags():
    assert failures(card(found=False), [{"found": False}]) == []
    assert failures(card(), [{"found": False}])
    assert failures(card(language_ok=False), [{"language_ok": False}]) == []


def test_count_is_max_and_min():
    two = card(issues=[("Data centers", True), ("Water use", False)])
    assert failures(two, [{"count": "issues", "is": 2}]) == []
    assert failures(two, [{"count": "issues", "max": 1}])
    assert failures(two, [{"count": "new_issues", "is": 1}]) == []
    assert failures(two, [{"count": "evidence", "min": 1}])


def test_count_of_stances_leaves_out_none():
    both = card(solutions=[(VETO, "Need for world government", "none"), ("Carbon tax", "Climate", "approve")])
    assert failures(both, [{"count": "stances", "is": 1}]) == []
    assert failures(both, [{"count": "solutions", "is": 2}]) == []


def test_issue_matches_by_key():
    assert failures(DATA_CENTERS, [{"issue": "data  centers"}]) == []
    assert failures(DATA_CENTERS, [{"issue": "Data center"}])


def test_solution_with_stance_and_issue():
    veto = card(solutions=[(VETO, "Security Council veto", "approve")])
    assert failures(veto, [{"solution": VETO, "stance": "approve", "for_issue": "Security Council veto"}]) == []
    assert failures(veto, [{"solution": VETO, "stance": ["approve", "none"]}]) == []
    assert failures(veto, [{"solution": VETO, "stance": "oppose"}])
    assert failures(veto, [{"solution": VETO, "for_issue": "Need for world government"}])


def test_evidence_with_every_field_given():
    assert failures(DATA_CENTERS, [{"evidence": ["electricity"], "url": None, "stance": "supports",
                                    "about": "Data centers"}]) == []
    assert failures(DATA_CENTERS, [{"evidence": ["electricity"], "stance": "refutes"}])
    assert failures(DATA_CENTERS, [{"about": ["Carbon tax", "Data centers"]}]) == []
    assert failures(DATA_CENTERS, [{"evidence": ["water"]}])


def test_a_list_name_matches_by_words():
    assert failures(DATA_CENTERS, [{"evidence": ["Electricity", "prices"]}]) == []
    assert failures(DATA_CENTERS, [{"evidence": ["electricity", "water"]}])


def test_not_of_an_absent_stance_holds():
    check = [{"not": {"solution": VETO, "stance": "oppose"}}]
    assert failures(card(solutions=[(VETO, "Need for world government", "none")]), check) == []
    assert failures(card(), check) == []
    assert failures(card(solutions=[(VETO, "Need for world government", "oppose")]), check)


def test_any_holds_when_one_group_holds():
    check = [{"any": [{"found": False}, {"all": [{"issue": "Data centers"}, {"count": "evidence", "is": 0}]}]}]
    assert failures(card(found=False), check) == []
    assert failures(card(issues=[("Data centers", True)]), check) == []
    assert failures(DATA_CENTERS, check)


def test_failure_lines_name_the_check():
    lines = failures(card(issues=[("Data centers", True)]),
                     [{"evidence": ["water"], "stance": "supports", "about": "Data centers"}])
    assert len(lines) == 1 and "evidence" in lines[0] and "Data centers" in lines[0]


def test_validate_refuses_an_unknown_key():
    with pytest.raises(ValueError, match="isue"):
        validate([{"isue": "x"}])


@pytest.mark.parametrize("check", [{"count": "people", "is": 1}, {"count": "issues"}, {"found": "yes"},
                                   {"solution": VETO, "stance": "maybe"}, {"evidence": 3},
                                   {"any": {"found": True}}, {"not": [{"found": True}]}, "found"])
def test_validate_refuses_a_malformed_check(check):
    with pytest.raises(ValueError):
        validate([check])
