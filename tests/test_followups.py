"""Follow-up questions (05_extraction.md, "Follow-up questions: the follow-up call"): the prompt, the fixed
missing source question, and the guard rails on the reading service's reply. No network."""

import json
import logging

import httpx

from app import followups
from app.config import Settings
from app.followups import MISSING_SOURCE, Row, follow_ups
from app.principles import guiding_block

STATEMENT = "Rents in our town doubled. The council should build homes. A survey showed it."


def settings(key="offline test key"):
    return Settings("test passphrase", "test secret", "test admin", "neo4j://localhost:7687", "neo4j", "test",
                    app_env="local", llm_api_key=key)


def replying(questions, calls=None, usage=None, raw=None, answered=()):
    def handler(request):
        if calls is not None:
            calls.append(json.loads(request.content))
        content = raw if raw is not None else json.dumps({"answered": list(answered), "questions": questions})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                         "usage": usage or {"prompt_tokens": 8600, "completion_tokens": 60,
                                                            "prompt_cache_hit_tokens": 6912}})
    return httpx.MockTransport(handler)


def q(row, name, kind="where", text="Where does this happen?"):
    return {"row": row, "name": name, "kind": kind, "text": text}


def test_the_prompt_opens_with_the_guiding_block_as_the_reading_does():
    from app.extract import SYSTEM_PROMPT as READING
    assert followups.SYSTEM_PROMPT.startswith("\n" + guiding_block() + "\n")
    # The same bytes up to the task rules, so the provider's prefix cache serves both calls.
    shared = len("\n" + guiding_block() + "\n")
    assert followups.SYSTEM_PROMPT[:shared] == READING[:shared]
    assert "Never ask for more detail about something the statement" in followups.SYSTEM_PROMPT


def test_the_user_message_carries_the_statement_and_the_new_rows_only_as_data():
    messages = followups.build_messages(STATEMENT, [Row("issue", "Rent rises"),
                                                    Row("evidence", "Survey", url="https://example.org/s")])
    body = json.loads(messages[1]["content"])
    assert body == {"statement": STATEMENT, "rows": [{"row": "issue", "name": "Rent rises"},
                                                     {"row": "evidence", "name": "Survey", "has_link": True}]}


def test_questions_are_kept_for_new_rows_by_name_in_the_replys_order():
    calls = []
    reply = [q("issue", "rent rises", "who", "Who is most affected by the rent rises?"),
             q("solution", "Build council homes", "who", "Who would pay for the new homes?")]
    result = follow_ups(STATEMENT, [Row("issue", "Rent rises"), Row("solution", "Build council homes")],
                        settings(), transport=replying(reply, calls))
    assert [(item["row"], item["name"], item["kind"]) for item in result.questions] == [
        ("issue", "Rent rises", "who"), ("solution", "Build council homes", "who")]
    assert result.status == "ok" and result.dropped == 0 and result.usage["prompt_cache_hit_tokens"] == 6912
    sent = calls[0]
    assert sent["max_tokens"] == 400 and sent["temperature"] == 0.1


def test_a_bad_question_is_dropped():
    rows = [Row("issue", "Rent rises"), Row("solution", "Build council homes"), Row("evidence", "Survey", url="https://x.org")]
    reply = [q("issue", "Something else"),                                   # not a listed row
             q("solution", "Build council homes", "what", "What is it?"),    # kind not in the list
             q("issue", "Rent rises", text="Where. Is it?"),                  # two sentences
             q("issue", "Rent rises", text="Where does this happen"),         # no question mark
             q("issue", "Rent rises", text="W" * 120 + "?"),                  # too long
             q("issue", "Rent rises", text="Where?\nWhen?"),                  # a line break
             q("solution", "Build council homes", "who", "What is your home address?"),  # private
             q("evidence", "Survey", "when", "When was the survey made?"),
             q("evidence", "Survey", "who", "Who ran the survey?"),           # a second for the same row
             "not a question"]
    result = follow_ups(STATEMENT, rows, settings(), transport=replying(reply))
    assert [item["text"] for item in result.questions] == ["When was the survey made?"]
    assert result.dropped == 9


def test_a_question_of_a_kind_the_reply_marks_answered_is_dropped():
    # The case run's lesson (F10): the reply says the statement answers who for a row, then asks who anyway.
    answered = [{"row": "solution", "name": "Build a flood wall", "kinds": ["who"]},
                {"row": "issue", "name": "River flooding", "kinds": "where"},  # not a list: ignored
                {"row": "issue", "name": 7, "kinds": ["where"]}]
    reply = [q("solution", "build a flood wall", "who", "Who would build the flood wall?"),
             q("issue", "River flooding", "where", "Where does the river flood?")]
    result = follow_ups(STATEMENT, [Row("issue", "River flooding"), Row("solution", "Build a flood wall")], settings(),
                        transport=replying(reply, answered=answered))
    assert [item["text"] for item in result.questions] == ["Where does the river flood?"]
    assert result.dropped == 1


def test_an_evidence_row_with_no_link_and_no_tick_always_gets_the_fixed_question_with_no_call():
    calls = []
    result = follow_ups(STATEMENT, [Row("evidence", "A survey")], settings(), transport=replying([], calls))
    assert result.questions == [{"row": "evidence", "name": "A survey", "kind": "where",
                                 "text": MISSING_SOURCE, "fixed": True}]
    assert calls == [] and not result.called


def test_the_fixed_question_counts_toward_three_and_its_row_is_not_sent():
    calls = []
    rows = [Row("evidence", "A survey"), Row("evidence", "My neighbour", personal=True),
            Row("issue", "Rent rises"), Row("solution", "Build council homes"), Row("issue", "Empty homes")]
    reply = [q("evidence", "A survey", text="When was it?"),  # its row was not asked
             q("evidence", "My neighbour", "when", "When did this happen?"),
             q("issue", "Rent rises", "who", "Who is affected?"),
             q("solution", "Build council homes", "who", "Who would build them?")]
    result = follow_ups(STATEMENT, rows, settings(), transport=replying(reply, calls))
    assert [item["text"] for item in result.questions] == [MISSING_SOURCE, "When did this happen?", "Who is affected?"]
    assert [row["name"] for row in json.loads(calls[0]["messages"][1]["content"])["rows"]] == [
        "My neighbour", "Rent rises", "Build council homes", "Empty homes"]
    assert json.loads(calls[0]["messages"][1]["content"])["rows"][0]["own_experience"] is True


def test_three_fixed_questions_leave_no_room_for_a_call():
    calls = []
    rows = [Row("evidence", f"Report {n}") for n in "abcd"] + [Row("issue", "Rent rises")]
    result = follow_ups(STATEMENT, rows, settings(), transport=replying([], calls))
    assert len(result.questions) == 3 and all(item["fixed"] for item in result.questions)
    assert calls == []


def test_without_a_reading_service_only_the_fixed_question_and_nothing_breaks():
    result = follow_ups(STATEMENT, [Row("issue", "Rent rises"), Row("evidence", "A survey")], settings(key=None))
    assert [item["text"] for item in result.questions] == [MISSING_SOURCE]
    assert result.status == "unconfigured" and not result.called


def test_a_limited_reader_gets_the_fixed_question_only():
    calls = []
    result = follow_ups(STATEMENT, [Row("issue", "Rent rises"), Row("evidence", "A survey")], settings(),
                        limited=lambda: True, transport=replying([q("issue", "Rent rises")], calls))
    assert result.status == "limited" and calls == [] and len(result.questions) == 1


def test_an_empty_statement_is_not_sent():
    calls = []
    result = follow_ups("  ", [Row("issue", "Rent rises")], settings(), transport=replying([], calls))
    assert result.questions == [] and calls == []


def test_a_reply_of_the_wrong_shape_gives_no_questions_never_an_error():
    for raw in ("not json", json.dumps({"questions": "none"}), json.dumps([1, 2])):
        result = follow_ups(STATEMENT, [Row("issue", "Rent rises"), Row("evidence", "A survey")], settings(),
                            transport=replying(None, raw=raw))
        assert result.status == "bad_reply" and [item["text"] for item in result.questions] == [MISSING_SOURCE]


def test_a_failing_service_is_asked_once():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)
    result = follow_ups(STATEMENT, [Row("issue", "Rent rises")], settings(), transport=httpx.MockTransport(handler))
    assert result.status == "failed" and result.questions == [] and len(calls) == 1


def test_the_log_line_has_counts_and_tokens_never_the_statement(caplog):
    caplog.set_level(logging.INFO)
    follow_ups(STATEMENT, [Row("issue", "Rent rises"), Row("evidence", "A survey")], settings(),
               request_id="r1", transport=replying([q("issue", "Rent rises", "who", "Who is affected?")]))
    lines = [json.loads(record.getMessage()) for record in caplog.records
             if record.levelno == logging.INFO and '"event": "follow_ups"' in record.getMessage()]
    assert lines == [{"event": "follow_ups", "request_id": "r1", "chars": len(STATEMENT), "new_rows": 2, "status": "ok",
                      "latency_ms": lines[0]["latency_ms"], "prompt_tokens": 8600, "prompt_cache_hit_tokens": 6912,
                      "completion_tokens": 60, "questions": 2, "questions_dropped": 0, "missing_source": 1}]
    assert all("Rents" not in record.getMessage() for record in caplog.records if record.levelno >= logging.INFO)
