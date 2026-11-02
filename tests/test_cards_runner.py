import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.extract import CardPayload, Extraction
from scripts import cards

FIXTURES = Path(__file__).parent / "fixtures"
GOOD = {"language_ok": True, "found": True, "issues": [{"name": "Data centers"}], "solutions": [], "evidence": []}
BAD = {"language_ok": True, "found": False, "issues": [], "solutions": [], "evidence": []}
CASE = {"id": "T1", "name": "Test", "context": "stlouis", "text": "Data centers are a problem.", "expect": "",
        "checks": [{"found": True}, {"issue": "Data centers"}]}


class Fake:
    """A reading that answers with the given cards in turn (None is no answer), from any thread."""

    def __init__(self, *answers):
        self.answers, self.lock, self.calls = list(answers), threading.Lock(), 0

    def extract(self, text, display_name, candidates, settings, *, writing_about=None):
        with self.lock:
            answer = self.answers[self.calls % len(self.answers)]
            self.calls += 1
        if answer is None:
            return None
        return Extraction(CardPayload.model_validate(answer), json.dumps(answer), "fake", 1)


def run(case, *readings, runs=3):
    with ThreadPoolExecutor(max_workers=4) as pool:
        return cards.run_case(case, cards.context_candidates(case, None), list(readings), runs, None, pool)


def test_a_case_meets_its_mark_when_every_run_passes(capsys):
    assert run(CASE, Fake(GOOD)) == [{"passed": 3, "runs": 3, "no_answer": 0, "misses": []}]
    assert cards.check([CASE], None, [Fake(GOOD)], 3, None) == 0
    assert "case T1   3/3   met" in capsys.readouterr().out


def test_a_pass_mark_of_two_allows_one_miss(capsys):
    assert cards.check([{**CASE, "pass": 2, "pass_note": "wobbles"}], None, [Fake(GOOD, BAD, GOOD)], 3, None) == 0
    assert cards.check([CASE], None, [Fake(GOOD, BAD, GOOD)], 3, None) == 1
    assert "MISSED" in capsys.readouterr().out


def test_a_run_with_no_answer_never_passes(capsys):
    [result] = run(CASE, Fake(GOOD, None, GOOD))
    assert result["passed"] == 2 and result["no_answer"] == 1
    assert cards.check([CASE], None, [Fake(GOOD, None, GOOD)], 3, None) == 3
    assert "1 run with no answer" in capsys.readouterr().out


def test_a_live_case_without_names_is_skipped(capsys):
    reading = Fake(GOOD)
    assert cards.check([{**CASE, "context": "live"}], None, [reading], 3, None) == 0
    assert reading.calls == 0
    assert "1 skipped (needs --names)" in capsys.readouterr().out


def test_a_local_case_makes_no_call(capsys):
    reading = Fake(GOOD)
    long = {**CASE, "id": "10", "text": "Long words here.", "words": 5000, "checks": "local"}
    assert cards.check([long], None, [reading], 3, None) == 0
    assert reading.calls == 0


def test_load_names_reads_an_api_candidates_body():
    names = cards.load_names(FIXTURES / "candidates_body.json")
    assert names.issues == {"library opening hours": {"name": "Library opening hours", "parent_key": None}}
    assert names.solution_issues["open the library on sundays"] == ["Library opening hours"]
    assert cards.context_candidates({**CASE, "context": "live"}, names) is names


def test_against_marks_a_case_worse(capsys):
    assert cards.check([CASE], None, [Fake(GOOD, BAD, BAD), Fake(GOOD)], 3, None, against="main") == 1
    assert "case T1   now 1/3   main 3/3   WORSE" in capsys.readouterr().out


def test_extra_cases_with_a_repeated_id_are_refused(tmp_path):
    extra = tmp_path / "live_cases.json"
    extra.write_text(json.dumps([{**CASE, "id": "29"}]))
    with pytest.raises(ValueError, match="29"):
        cards.load_cases([extra])
    extra.write_text(json.dumps([{**CASE, "id": "L1"}]))
    assert cards.load_cases([extra])[-1]["id"] == "L1"
