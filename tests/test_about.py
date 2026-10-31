"""Phase 3: the About page (04_interface.md, "About"). Nothing read from the record but the signed-in account, no reading service."""

import re

import pytest
from markupsafe import escape

from app import principles, routes_about

# "language model" is John's own wording for this page (28 October); any other "model" is still out.
FORBIDDEN = re.compile(r"\b(node|edge|graph|cypher|(?<!language )model|extraction|entity)s?\b", re.I)


@pytest.fixture
def about(member_app, switch):
    # member_app already fails any test that opens a database, so the page reads nothing from the record.
    switch(about_enabled=True, llm_api_key="private-test-key", llm_base_url="https://api.deepseek.com",
           llm_model="deepseek-v4-flash")
    return member_app


def own_words(html: str) -> str:
    """The page's own copy: everything inside <main>, without the three documents and the repository address."""
    body = html.split('<main class="column">', 1)[1].split("</main>", 1)[0]
    body = re.sub(r'<div class="guiding-text">.*?</div>', "", body, flags=re.S)
    return re.sub(r"<[^>]+>", " ", body.replace(routes_about.REPOSITORY, ""))


def test_switch_off_means_not_found(member_app):
    assert member_app.client.get("/about").status_code == 404


def test_it_opens_without_signing_in(about):
    response = about.client.get("/about", follow_redirects=False)
    assert response.status_code == 200
    assert "<h1>About this site</h1>" in response.text


def test_it_opens_without_signing_in_with_the_passphrase_too(about, switch):
    switch(accounts_enabled=False)
    assert about.client.get("/about", follow_redirects=False).status_code == 200


def test_the_three_documents_are_the_files_the_instructions_use(about):
    html = about.client.get("/about").text
    shown = re.findall(r'<div class="guiding-text">(.*?)</div>', html, flags=re.S)
    assert shown == [str(escape(principles.PURPOSE)), str(escape(principles.UDHR)), str(escape(principles.EARTH_CHARTER))]
    for text in (principles.PURPOSE, principles.UDHR, principles.EARTH_CHARTER):
        assert text in principles.guiding_block()
    assert [re.sub(r"<[^>]+>", "", h) for h in re.findall(r"<h3>(.*?)</h3>", html)] == [
        "Statement of purpose", "Universal Declaration of Human Rights", "The Earth Charter"]


def test_it_names_the_reading_service_and_its_version(about):
    html = about.client.get("/about").text
    assert "<p>DeepSeek, version deepseek-v4-flash. It reads statements," in html
    assert routes_about.NO_READING_SERVICE not in html
    assert "private-test-key" not in html


def test_without_a_key_it_says_no_reading_service_is_set_up(about, switch):
    switch(llm_api_key=None)
    html = about.client.get("/about").text
    assert f"<p>{routes_about.NO_READING_SERVICE_CARDS}</p>" in html
    assert "DeepSeek" not in html
    switch(ask_enabled=True)
    assert f"<p>{routes_about.NO_READING_SERVICE}</p>" in about.client.get("/about").text


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", own_words(html))


def test_with_ask_and_follow_ups_off_it_speaks_only_of_reading_statements(about):
    words = text_of(about.client.get("/about").text)
    assert "question" not in words.lower() and "follow-up" not in words
    assert "evidence link" not in words
    assert "It reads statements, with the guiding principles below" in words
    assert "at the start of the system prompt, its instructions for reading statements. They guide it" in words
    assert "It does not judge a post against them, and names an article or a principle only when a post does." in words
    assert "The statement being written and its form; and the names of issues, solutions and evidence." in words
    assert "the first page after one can take up to a minute" in words
    assert "everyone here can read and build on." in words


def test_with_every_part_on_it_reads_as_04_has_it(about, switch):
    switch(ask_enabled=True, follow_ups_enabled=True, evidence_check_enabled=True)
    words = text_of(about.client.get("/about").text)
    for sentence in (
            "everyone here can read, ask questions of, and build on.",
            " How statements are read and questions are answered ",
            "When you ask a question, the site gathers what the database holds about it:",
            "It reads statements, answers questions and suggests follow-up questions, with the guiding principles below "
            "at the start of its instructions each time. When it checks the page behind an evidence link it is given "
            "no principles, so that each link stays quick and cheap to read.",
            "The statement being written and its form; the question and your earlier questions on the page; and what the "
            "database holds that an answer is built from:",
            "the first page or question after one can take up to a minute.",
            "at the start of the system prompt, its instructions for reading statements, answering questions and asking "
            "follow-up questions.",
            "It does not judge a post against them unless a question asks, and names an article or a principle only when "
            "the question or a post does.",
            # John, 30 October: answers are short and kept with their question.
            "The language model writes an answer of two or three sentences from that alone, or a longer one when the "
            "question asks for more,",
            "A question that gets an answer is kept with its answer and listed under the Ask box for everyone here, "
            "without the name of who asked; a listed question opens the answer it got, while the posts it rests on "
            "are unchanged."):
        assert sentence in words, sentence
    assert "Answers are not kept." not in words


@pytest.mark.parametrize("fields, reads, given", [
    ({"ask_enabled": True}, "It reads statements and answers questions,",
     "instructions for reading statements and answering questions."),
    ({"follow_ups_enabled": True}, "It reads statements and suggests follow-up questions,",
     "instructions for reading statements and asking follow-up questions.")])
def test_each_switch_adds_only_its_own_part(about, switch, fields, reads, given):
    switch(**fields)
    words = text_of(about.client.get("/about").text)
    assert reads in words and given in words
    assert ("When you ask a question" in words) is ("ask_enabled" in fields)


@pytest.mark.parametrize("url, name", [("https://api.deepseek.com", "DeepSeek"),
                                       ("https://api.openai.com/v1", "OpenAI"),
                                       ("https://reader.example.org/v1", "reader.example.org"),
                                       ("https://api.provider.example/v1", "provider.example")])
def test_provider_comes_from_the_base_address(url, name):
    assert routes_about.provider(url) == name


def test_it_names_johns_repository_and_the_site_name(about, switch):
    switch(ask_enabled=True)
    html = about.client.get("/about").text
    assert f'<a href="{routes_about.REPOSITORY}" rel="noopener noreferrer">' in html
    # John's wording of 31 October, word for word with Ask on.
    assert (f"<p>{about.settings.site_name} is a small test of a conversational platform for constructing a shared database"
            " of issues, evidence, and solutions for collective problem solving. People write statements about issues they"
            " care about. The site reads each statement, and extracts the issues, evidence, and solutions into a short form;"
            " the person checks and corrects the form; and it joins a database that everyone here can read, ask questions of,"
            " and build on. Development of this prototype software began in September of 2026.</p>") in html


def test_its_own_copy_has_no_technical_words_or_dashes(about):
    words = own_words(about.client.get("/about").text)
    assert FORBIDDEN.search(words) is None, FORBIDDEN.search(words)
    assert "–" not in words and "—" not in words and " - " not in words
    # John's wording throughout this page (28 October): database, form and language model.
    assert re.search(r"\brecord\b|\bcards?\b|reading service", words) is None, re.search(r"\brecord\b|\bcards?\b|reading service", words)


def test_the_menu_shows_about_on_its_own_page(about):
    html = about.client.get("/about").text
    assert '<a href="/about">About</a></nav>' in html


def test_a_signed_in_member_gets_the_whole_menu_here_too(about, switch):
    # John, 28 October: About dropped Enter a person, My statements and My account; every other page has all seven.
    about.sign_in()
    switch(ask_enabled=True)
    nav = re.search(r"<nav>.*?</nav>", about.client.get("/about").text).group(0)
    assert nav == ('<nav><a href="/">Write</a><a href="/issues">Issues</a><a href="/ask">Ask</a>'
                   '<a href="/people">Enter a person</a><a href="/my-statements">My statements</a>'
                   '<a href="/account">My account</a><a href="/about">About</a></nav>')


def test_signed_out_it_keeps_the_short_menu(about):
    nav = re.search(r"<nav>.*?</nav>", about.client.get("/about").text).group(0)
    assert "/my-statements" not in nav and "/account" not in nav and "/people" not in nav


# John, call of 28 October: someone without an invitation can find About from the sign in page.
def test_the_sign_in_page_links_here(about):
    assert '<p><a href="/about">About this site</a></p>' in about.client.get("/sign-in").text


def test_switched_off_the_sign_in_page_has_no_link(member_app):
    assert 'href="/about"' not in member_app.client.get("/sign-in").text
