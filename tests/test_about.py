"""Phase 3: the About page (04_interface.md, "About"). No database, no reading service."""

import re

import pytest
from markupsafe import escape

from app import principles, routes_about

FORBIDDEN = re.compile(r"\b(node|edge|graph|cypher|model|extraction|entity)s?\b", re.I)


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
    assert f"<p>{routes_about.NO_READING_SERVICE}</p>" in html
    assert "DeepSeek" not in html


@pytest.mark.parametrize("url, name", [("https://api.deepseek.com", "DeepSeek"),
                                       ("https://api.openai.com/v1", "OpenAI"),
                                       ("https://reader.example.org/v1", "reader.example.org"),
                                       ("https://api.provider.example/v1", "provider.example")])
def test_provider_comes_from_the_base_address(url, name):
    assert routes_about.provider(url) == name


def test_it_names_johns_repository_and_the_site_name(about):
    html = about.client.get("/about").text
    assert f'<a href="{routes_about.REPOSITORY}" rel="noopener noreferrer">' in html
    assert f"<p>{about.settings.site_name} is a small test of a shared record." in html


def test_its_own_copy_has_no_technical_words_or_dashes(about):
    words = own_words(about.client.get("/about").text)
    assert FORBIDDEN.search(words) is None, FORBIDDEN.search(words)
    assert "–" not in words and "—" not in words and " - " not in words


def test_the_menu_shows_about_on_its_own_page(about):
    html = about.client.get("/about").text
    assert '<a href="/about">About</a></nav>' in html
