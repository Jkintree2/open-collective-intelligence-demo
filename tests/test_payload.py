"""Field rules from docs/planning/05_extraction.md, applied server side to the card payload."""

from app.extract import Candidates, CardPayload, resolve_payload

ISSUE = "Rising sea levels threaten coastal housing"

CANDIDATES = Candidates(
    issues={
        "need for world government": {"name": "Need for world government", "parent_key": None},
        "security council veto": {
            "name": "Security Council veto",
            "parent_key": "need for world government",
        },
    },
    solutions={"limit or abolish the security council veto": "Limit or abolish the Security Council veto"},
    evidence={"un charter article 27": "UN Charter, Article 27"},
)


def _payload(**kwargs):
    base = {"issues": [{"name": ISSUE, "parent": None}], "solutions": [], "evidence": []}
    base.update(kwargs)
    return CardPayload.model_validate(base)


def test_a_url_that_is_not_http_becomes_null():
    payload = _payload(
        evidence=[
            {"name": "2024 NOAA survey", "url": "javascript:alert(1)", "stance": "supports", "about": ISSUE},
            {"name": "Earth Charter", "url": "https://earthcharter.org/", "stance": "supports", "about": ISSUE},
        ]
    )
    resolved = resolve_payload(payload, Candidates.empty())
    assert resolved.evidence[0]["url"] is None
    assert resolved.evidence[1]["url"] == "https://earthcharter.org/"


def test_unknown_for_issue_falls_back_to_the_first_issue():
    payload = _payload(solutions=[{"name": "Seawall in the harbor district", "for_issue": "Nowhere", "stance": "none"}])
    resolved = resolve_payload(payload, Candidates.empty())
    assert resolved.solutions[0]["for_issue_key"] == "rising sea levels threaten coastal housing"


def test_lists_are_capped_at_three_issues_and_five_solutions_and_five_evidence():
    payload = _payload(
        issues=[{"name": f"Issue number {n}", "parent": None} for n in range(6)],
        solutions=[{"name": f"Solution number {n}", "for_issue": None, "stance": "none"} for n in range(8)],
        evidence=[{"name": f"Evidence number {n}", "url": None, "stance": "supports", "about": None} for n in range(8)],
    )
    resolved = resolve_payload(payload, Candidates.empty())
    assert len(resolved.issues) == 3
    assert len(resolved.solutions) == 5
    assert len(resolved.evidence) == 5


def test_names_are_cleaned_and_keyed_and_unusable_names_dropped():
    payload = _payload(
        issues=[{"name": "the security council veto.\n", "parent": None}, {"name": "!!!", "parent": None}]
    )
    resolved = resolve_payload(payload, CANDIDATES)
    assert len(resolved.issues) == 1
    assert resolved.issues[0]["name"] == "Security Council veto"
    assert resolved.issues[0]["key"] == "security council veto"
    assert resolved.issues[0]["existing"] is True


def test_a_parent_that_is_a_sub_issue_is_replaced_by_its_own_parent():
    payload = _payload(issues=[{"name": "Veto reform timetable", "parent": "Security Council veto"}])
    resolved = resolve_payload(payload, CANDIDATES)
    assert resolved.issues[0]["parent_key"] == "need for world government"


def test_a_parent_that_does_not_exist_is_dropped():
    payload = _payload(issues=[{"name": "Veto reform timetable", "parent": "Nowhere"}])
    resolved = resolve_payload(payload, CANDIDATES)
    assert resolved.issues[0]["parent_key"] is None


def test_a_parent_introduced_by_the_same_card_is_kept():
    payload = _payload(issues=[{"name": "Coastal flooding"},
                               {"name": "Harbor district drainage", "parent": "Coastal flooding"}])
    resolved = resolve_payload(payload, Candidates.empty())
    assert [item["parent_key"] for item in resolved.issues] == [None, "coastal flooding"]
    assert not resolved.dropped and not resolved.corrected


def test_a_missing_parent_is_a_correction_and_does_not_stop_the_post():
    resolved = resolve_payload(_payload(issues=[{"name": "Veto reform timetable", "parent": "Nowhere"}]), CANDIDATES)
    assert resolved.issues[0]["parent_key"] is None
    assert not resolved.dropped and len(resolved.corrected) == 1


def test_short_names_are_reused_when_they_exist_and_refused_when_they_are_new():
    known = Candidates(issues={"ai": {"name": "AI", "parent_key": None}})
    resolved = resolve_payload(_payload(issues=[{"name": "AI"}, {"name": "EU"}]), known)
    assert [item["key"] for item in resolved.issues] == ["ai"]
    assert resolved.issues[0]["existing"] is True
    assert resolved.dropped == ["issue 'EU'"]


def test_a_reference_to_a_short_existing_issue_is_not_repointed():
    known = Candidates(issues={"ai": {"name": "AI", "parent_key": None}})
    payload = _payload(issues=[{"name": ISSUE}],
                       solutions=[{"name": "Publish the training data", "for_issue": "AI"}])
    resolved = resolve_payload(payload, known)
    assert resolved.solutions[0]["for_issue_key"] == "ai"


def test_evidence_about_a_solution_in_the_payload_targets_that_solution():
    payload = _payload(
        solutions=[{"name": "Seawall in the harbor district", "for_issue": ISSUE, "stance": "approve"}],
        evidence=[{"name": "Harbor study", "url": None, "stance": "refutes", "about": "Seawall in the harbor district"}],
    )
    resolved = resolve_payload(payload, Candidates.empty())
    assert resolved.evidence[0]["target_label"] == "Solution"
    assert resolved.evidence[0]["target_key"] == "seawall in the harbor district"
    assert resolved.evidence[0]["stance"] == "refutes"
    assert resolved.solutions[0]["stance"] == "approve"


def test_bad_stances_are_corrected_not_rejected():
    payload = CardPayload.model_validate(
        {
            "issues": [{"name": ISSUE}],
            "solutions": [{"name": "Seawall", "for_issue": ISSUE, "stance": "strongly"}],
            "evidence": [{"name": "Study", "stance": "maybe", "about": ISSUE}],
        }
    )
    assert payload.solutions[0].stance == "none"
    assert payload.evidence[0].stance == "supports"


def test_a_solution_with_no_issue_anywhere_is_dropped():
    payload = CardPayload.model_validate(
        {"issues": [], "solutions": [{"name": "Seawall", "for_issue": None, "stance": "none"}], "evidence": []}
    )
    resolved = resolve_payload(payload, Candidates.empty())
    assert resolved.solutions == []
    assert resolved.is_empty


def test_cleared_and_malformed_names_do_not_reject_other_rows():
    payload = _payload(issues=[{"name": ""}, {"name": None}, {"name": 42}, {"name": ISSUE}])
    resolved = resolve_payload(payload, Candidates.empty())
    assert [item["name"] for item in resolved.issues] == [ISSUE]


def test_existing_sub_issue_keeps_its_parent_even_when_card_omits_it():
    resolved = resolve_payload(_payload(issues=[{"name": "Security Council veto"}]), CANDIDATES)
    assert resolved.issues[0]["parent_key"] == "need for world government"


def test_existing_parent_cannot_be_made_a_child_and_new_parents_are_not_invented():
    payload = _payload(issues=[{"name": "Need for world government", "parent": "Security Council veto"},
                               {"name": "New issue", "parent": "Another new issue"},
                               {"name": "Another new issue", "parent": "New issue"}])
    resolved = resolve_payload(payload, CANDIDATES)
    assert all(item["parent_key"] is None for item in resolved.issues)


def test_empty_and_non_english_results_cannot_retain_structure():
    for flags in ({"found": False}, {"language_ok": False}):
        payload = CardPayload.model_validate({"issues": [{"name": ISSUE}], **flags})
        assert payload.issues == []


def test_invalid_http_urls_are_removed():
    payload = _payload(evidence=[{"name": "Study", "about": ISSUE, "url": "https://"}])
    assert payload.evidence[0].url is None


def test_a_childless_top_level_issue_can_gain_a_parent_new_on_the_same_card():
    known = Candidates(issues={"short term rental properties": {"name": "Short term rental properties", "parent_key": None}})
    payload = _payload(issues=[{"name": "Downtown St Louis revitalization", "parent": None},
                               {"name": "Short term rental properties", "parent": "Downtown St Louis revitalization"}])
    resolved = resolve_payload(payload, known)
    assert [item["parent_key"] for item in resolved.issues] == [None, "downtown st louis revitalization"]
    assert not resolved.corrected
