"""v0.3: Home's routes. home.js asks POST /api/home/kind what a text is; without JavaScript the box posts to /home,
where a statement is posted as POST /posts posts it, a question is answered as POST /ask answers it, and an unsure
text comes back with two buttons. The box on Issues, My statements and About posts to /home with start set, and
Home carries on with the text. No database, no language model: the Ask fixture stubs the answer."""

import pytest

from app.auth import PostSpacing
from app.home import kind_of
from test_ask_routes import ANSWERED, SAME_SITE, asking  # noqa: F401  the Ask fixture, answer stubbed

UNSURE = "What we need is a global referendum."
QUESTION = "Why do people oppose these solutions?"
STATEMENT = "data centers raise electricity prices"


@pytest.fixture
def homing(asking, switch, monkeypatch):
    raw = []
    monkeypatch.setattr(asking.main.graph, "create_raw_post", lambda *args: raw.append(args))
    monkeypatch.setattr(asking.main, "post_spacing", PostSpacing(seconds=0))
    asking.raw = raw
    switch(home_enabled="on")
    return asking


def kind(client, text, headers=SAME_SITE):
    return client.post("/api/home/kind", json={"text": text}, headers=headers)


def home(client, headers=SAME_SITE, **fields):
    return client.post("/home", data=fields, headers=headers, follow_redirects=False)


def answered(homing):
    return [call for call in homing.calls if call[0] == "answer"]


def test_the_cases_cover_each_kind():
    assert [kind_of(QUESTION), kind_of(STATEMENT), kind_of(UNSURE)] == ["question", "statement", "unsure"]


def test_kind_api(homing):
    for text, expected in ((QUESTION, "question"), (STATEMENT, "statement"), (UNSURE, "unsure"), ("", "statement")):
        response = kind(homing.client, text)
        assert response.status_code == 200
        assert response.json() == {"kind": expected}, text
    assert homing.raw == [] and homing.calls == []


def test_kind_api_over_the_write_limit_is_a_statement(homing):
    """The write path then gives its own too-long message."""
    assert kind(homing.client, "Why " * 1001 + "?").json() == {"kind": "statement"}


@pytest.mark.parametrize("mode, preview", [("off", ()), ("preview", ("someone@example.org",))])
def test_kind_api_404_when_off(homing, switch, mode, preview):
    switch(home_enabled=mode, home_preview=preview)
    assert kind(homing.client, QUESTION).status_code == 404
    assert home(homing.client, text=QUESTION).status_code == 404
    assert homing.raw == [] and homing.calls == []


def test_preview_member_gets_the_routes(homing, switch):
    switch(home_enabled="preview", home_preview=("ada@example.org",))
    assert kind(homing.client, QUESTION).json() == {"kind": "question"}


def test_signed_out_goes_to_the_door(homing):
    homing.client.cookies.clear()
    response = home(homing.client, text=QUESTION)
    assert response.status_code in (303, 307) and response.headers["location"].startswith("/sign-in")
    assert homing.raw == [] and homing.calls == []


def test_home_post_question_answers_like_ask(homing):
    response = home(homing.client, text=QUESTION)
    assert response.status_code == 200
    assert "One writer says the veto &lt;blocks&gt; action." in response.text
    assert answered(homing) == [("answer", QUESTION, [], "record")]
    assert homing.kept == [(QUESTION, None)]
    assert homing.raw == []


def test_home_post_statement_posts_like_posts(homing):
    response = home(homing.client, text=f"  {STATEMENT}  ")
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert [args[-1] for args in homing.raw] == [STATEMENT]
    assert homing.calls == []


def test_home_post_statement_keeps_the_anonymous_box(homing):
    home(homing.client, text=STATEMENT, anonymous="on")
    assert homing.raw[0][2] is True


def test_home_post_unsure_shows_both_buttons(homing):
    response = home(homing.client, text=UNSURE)
    assert response.status_code == 200
    page = response.text
    assert "Is this a statement to post, or a question to ask?" in page
    assert '<button type="submit" name="kind" value="statement" class="primary">Post it</button>' in page
    assert '<button type="submit" name="kind" value="question" class="primary">Ask it</button>' in page
    assert f">{UNSURE}</textarea>" in page
    assert 'action="/home"' in page
    assert homing.raw == [] and homing.calls == []


def test_each_unsure_button_does_what_it_says(homing):
    assert home(homing.client, text=UNSURE, kind="statement").status_code == 303
    assert [args[-1] for args in homing.raw] == [UNSURE]
    assert home(homing.client, text=UNSURE, kind="question").status_code == 200
    assert answered(homing) == [("answer", UNSURE, [], "record")]


def test_long_question_choice_gets_asks_message(homing):
    """Review Focus 2: a question over 500 characters is unsure; "Ask it" shows Ask's own message, never a cut."""
    text = "How does " + "the veto and " * 60 + "homelessness relate to the UDHR?"
    assert kind_of(text) == "unsure"
    response = home(homing.client, text=text, kind="question")
    assert response.status_code == 400
    assert "Please keep the question under 500 characters." in response.text
    assert homing.calls == [] and homing.raw == []


def test_ask_off_everything_posts(homing, switch):
    """Review Focus 5: with ASK_ENABLED off, Home only posts."""
    switch(ask_enabled=False)
    assert kind(homing.client, QUESTION).json() == {"kind": "statement"}
    assert kind(homing.client, UNSURE).json() == {"kind": "statement"}
    for text, choice in ((QUESTION, ""), (UNSURE, ""), (QUESTION, "question")):
        assert home(homing.client, text=text, kind=choice).status_code == 303
    assert [args[-1] for args in homing.raw] == [QUESTION, UNSURE, QUESTION]
    assert homing.calls == []


def test_too_long_comes_back_with_the_write_message(homing):
    response = home(homing.client, text="x" * 4001)
    assert response.status_code == 413
    assert "Please shorten it to a few paragraphs." in response.text
    assert homing.raw == []


def test_empty_goes_home(homing):
    response = home(homing.client, text="   ")
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert homing.raw == [] and homing.calls == []


def test_box_from_another_page_starts_on_home(homing):
    response = home(homing.client, text=QUESTION, start="1")
    assert response.status_code == 200
    assert f">{QUESTION}</textarea>" in response.text
    assert "data-start" in response.text
    assert homing.raw == [] and homing.calls == []


def test_without_javascript_a_question_from_an_issue_page_is_asked_about_it(homing):
    """John, 9 November: the box on an issue page carries the issue; without JavaScript the question is asked there."""
    response = home(homing.client, text=QUESTION, issue="veto")
    assert response.status_code == 200 and ("issue", "veto") in homing.calls


def test_unsure_keeps_the_item(homing):
    """Review, 9 November: when the site can't tell, Home comes back with the item still on it."""
    response = home(homing.client, text=UNSURE, issue="veto")
    form = response.text.split('id="compose"', 1)[1].split("</form>", 1)[0]
    assert 'id="about-issue"' in response.text and '<input type="hidden" name="issue" value="veto">' in form


def test_cross_site_refused(homing):
    cross = {"sec-fetch-site": "cross-site"}
    assert kind(homing.client, QUESTION, headers=cross).status_code == 403
    assert home(homing.client, headers=cross, text=STATEMENT).status_code == 403
    assert homing.raw == [] and homing.calls == []


def test_text_never_in_redirect_url(homing):
    for fields in ({"text": STATEMENT}, {"text": "   "}, {"text": UNSURE, "kind": "statement"}):
        response = home(homing.client, **fields)
        location = response.headers.get("location", "")
        assert "electricity" not in location and "referendum" not in location and "?" not in location
