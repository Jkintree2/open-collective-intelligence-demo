"""Revision round: one statement's reading under a piece of evidence on the issue page, rendered from
_confidence.html (04_interface.md, "Revision round: agrees, partly agrees, contradicts"). No database."""


from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Environment(loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "app" / "templates"),
                        autoescape=select_autoescape(["html"]))


def render(item):
    return TEMPLATES.get_template("_confidence.html").render(item=item)


def test_a_partly_reading_shows_both_sentences_and_what_the_page_does_not_say():
    html = render({"source_note": None, "confidence": None, "differs": None, "readings": [
        {"word": "Partly agrees", "claim": "It became <law>.", "quote": "It led to action.", "reason": "Not law."}]})
    assert html == ('<span class="confidence reading"><span class="reading-word">Partly agrees.</span> '
                    '<span class="reading-said">The statement says: <q>It became &lt;law&gt;.</q></span> '
                    '<span class="reading-said">The page says: <q>It led to action.</q></span> '
                    '<span class="reading-reason">Not law.</span></span>')


def test_no_writers_sentence_leaves_the_statement_line_out_and_no_link_says_so():
    html = render({"source_note": "No source given.", "confidence": None, "differs": None, "readings": [
        {"word": "Agrees", "claim": None, "quote": "Floods doubled.", "reason": None}]})
    assert html.startswith('<span class="confidence">No source given.</span>')
    assert "The statement says" not in html and "The page says: <q>Floods doubled.</q>" in html


def test_an_item_without_these_keys_renders_nothing():
    assert render({}) == ""
