import hashlib
import json

import httpx
import pytest

from app import extract as reading
from app import principles
from app.extract import Candidates
from tests.test_reading import CARD, SETTINGS

# SHA-256 of the reading prompt as it stood in app/extract.py before the guiding texts moved
# to app/guiding/ (main 995ee8f). If John changes a guiding file or the reading rules on purpose,
# the new hash goes here in the same commit.
PROMPT_SHA256 = "122df111cbe8b000da80530b3ae3dad1a0741acd545d6d08d7b59cf53c60e98d"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_reading_prompt_is_byte_for_byte_unchanged():
    assert sha(reading.SYSTEM_PROMPT) == PROMPT_SHA256
    assert len(reading.SYSTEM_PROMPT) == 32455


def test_the_prompt_sent_to_the_model_is_unchanged():
    sent = []

    def respond(request):
        sent.append(json.loads(request.content)["messages"])
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(CARD)}}]})

    reading.extract("Coastal flooding", "Tester", Candidates.empty(), SETTINGS, transport=httpx.MockTransport(respond))
    assert sent[0][0]["role"] == "system"
    assert sha(sent[0][0]["content"]) == PROMPT_SHA256


def test_guiding_block_is_purpose_then_both_documents_then_the_handover():
    block = principles.guiding_block()
    assert block.startswith("You are helping to create collective human and digital intelligence")
    assert block.index(principles.UDHR) < block.index(principles.EARTH_CHARTER)
    assert principles.UDHR.startswith("Universal Declaration of Human Rights\nPreamble")
    assert principles.UDHR.endswith("destruction of any of the rights and freedoms set forth herein.")
    assert principles.EARTH_CHARTER.startswith("THE EARTH CHARTER\nPREAMBLE")
    assert principles.EARTH_CHARTER.endswith("For more information, please visit www.EarthCharter.org.")
    assert block.endswith("\n\nNow, here are more detailed instructions for you to use to fulfill the purpose of this platform.")
    assert reading.SYSTEM_PROMPT == "\n" + block + "\n" + reading.READING_RULES


@pytest.mark.parametrize("name", ["purpose.txt", "udhr.txt", "earth_charter.txt"])
def test_an_edited_file_keeps_its_text_whatever_the_line_ends(tmp_path, monkeypatch, name):
    original = (principles.GUIDING / name).read_text(encoding="utf-8")
    (tmp_path / name).write_text(original.rstrip("\n").replace("\n", "\r\n") + "\r\n\r\n", encoding="utf-8", newline="")
    monkeypatch.setattr(principles, "GUIDING", tmp_path)
    assert principles._read(name) == original.strip()


def test_call_model_defaults_keep_two_attempts_of_25_seconds():
    calls = []

    def respond(request):
        calls.append(request.extensions["timeout"])
        return httpx.Response(503)

    assert reading.call_model([], SETTINGS, transport=httpx.MockTransport(respond)) is None
    assert len(calls) == 2
    assert calls[0] == {"connect": 5, "read": 25, "write": 25, "pool": 25}


def test_call_model_takes_one_attempt_and_its_own_timeout():
    calls = []

    def respond(request):
        calls.append(request.extensions["timeout"])
        return httpx.Response(503)

    assert reading.call_model([], SETTINGS, transport=httpx.MockTransport(respond), timeout=40, attempts=1) is None
    assert len(calls) == 1
    assert calls[0]["read"] == 40 and calls[0]["connect"] == 5
