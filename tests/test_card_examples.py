import json
from pathlib import Path

import pytest

from app.extract import Candidates, CardPayload, resolve_payload
from app.text import sentences

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "cards.json").read_text())


def test_drug_policy_sentences_match_the_six_acceptance_lines():
    assert sentences(CardPayload.model_validate(FIXTURES["1"]), "John Kintree") == [
        "John Kintree claims Drug dealing problem",
        "John Kintree proposes Decriminalize drug sales",
        "John Kintree proposes Treat drug use as medical issue",
        "Drug dealing problem has proposed Decriminalize drug sales",
        "Drug dealing problem has proposed Treat drug use as medical issue",
        "John Kintree approves Treat drug use as medical issue",
    ]


def test_seawall_sentences_match_the_five_acceptance_lines():
    assert sentences(CardPayload.model_validate(FIXTURES["4"]), "Tester") == [
        "Tester claims Rising sea levels threaten coastal housing",
        "Tester proposes Seawall in the harbor district",
        "Rising sea levels threaten coastal housing has proposed Seawall in the harbor district",
        "Tester submits 2024 NOAA flooding survey",
        "2024 NOAA flooding survey supports Rising sea levels threaten coastal housing",
    ]


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
