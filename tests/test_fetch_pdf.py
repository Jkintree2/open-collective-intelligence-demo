"""PDFs behind evidence links: read by content type, size, page and time limits, no text, arXiv. No network."""

import gzip
import sys
import time
from pathlib import Path

import pytest

from app import fetch_pdf
from app.fetch_page import MAX_CHARS, fetch
from make_pdf import REPORT, make_pdf
from test_fetch_page import resolver, serving

PDFS = Path(__file__).parent / "fixtures" / "pdfs"
PDF = "application/pdf"


def pdf_reply(data, content_type=PDF, **headers):
    return 200, {"content-type": content_type, **headers}, data


def read(url, routes, **kwargs):
    return fetch(url, resolver=resolver({}), transport=serving(routes), **kwargs)


@pytest.mark.parametrize("path,content_type", [
    ("/reports/flood-review", PDF),          # by content type alone, no .pdf ending
    ("/reports/flood-review.pdf", PDF),
    ("/reports/flood-review.pdf", "application/x-pdf"),
    ("/reports/flood-review.pdf", "application/octet-stream"),
])
def test_a_pdf_is_read_like_a_page(path, content_type):
    routes = {("gov.example.org", path): pdf_reply((PDFS / "flood_report.pdf").read_bytes(), content_type)}
    page = read("https://gov.example.org" + path, routes)
    assert page.status == "ok"
    assert "saw flood damage fall by a third" in page.text
    assert page.title == "Coastal Flood Resilience Review 2024"
    assert page.published == "2024-06-11"


def test_octet_stream_without_a_pdf_ending_is_not_read():
    routes = {("example.org", "/file"): pdf_reply(b"%PDF-1.4 whatever", "application/octet-stream")}
    assert read("https://example.org/file", routes).status == "unsupported"


def test_the_last_change_date_stands_in_when_there_is_no_creation_date():
    data = make_pdf(REPORT, modified="D:20230102000000Z")
    page = read("https://gov.example.org/r", {("gov.example.org", "/r"): pdf_reply(data)})
    assert page.status == "ok" and page.published == "2023-01-02" and page.title is None


def test_a_compressed_reply_is_unpacked():
    data = gzip.compress((PDFS / "flood_report.pdf").read_bytes())
    page = read("https://gov.example.org/r", {("gov.example.org", "/r"): pdf_reply(data, **{"content-encoding": "gzip"})})
    assert page.status == "ok" and "salt marsh" in page.text


def test_a_scanned_pdf_has_no_text():
    routes = {("gov.example.org", "/minutes.pdf"): pdf_reply((PDFS / "scanned.pdf").read_bytes())}
    page = read("https://gov.example.org/minutes.pdf", routes)
    assert page.status == "unread" and page.reason == "no_text"


def test_a_broken_pdf_is_not_read():
    page = read("https://gov.example.org/r", {("gov.example.org", "/r"): pdf_reply(b"%PDF-1.4\nnot really a pdf")})
    assert page.status == "unread" and page.reason == "pdf"


def test_only_the_first_forty_pages_are_read():
    data = make_pdf([f"This is page number {n} of the long report, marker{n}x." for n in range(1, 46)])
    page = read("https://gov.example.org/long", {("gov.example.org", "/long"): pdf_reply(data)})
    assert page.status == "ok"
    assert "marker40x" in page.text and "marker41x" not in page.text


def test_a_pdf_over_the_size_stop_is_not_read(monkeypatch):
    monkeypatch.setattr(fetch_pdf, "MAX_BYTES", 1000)
    data = make_pdf(REPORT * 5)
    assert len(data) > 1000
    page = read("https://gov.example.org/big.pdf", {("gov.example.org", "/big.pdf"): pdf_reply(data)})
    assert page.status == "unread" and page.reason == "too_big"


def test_the_size_stop_is_fifteen_megabytes_and_forty_pages():
    assert fetch_pdf.MAX_BYTES == 15_000_000 and fetch_pdf.MAX_PAGES == 40


def test_a_pdf_that_takes_too_long_is_stopped():
    started = time.perf_counter()
    slow = [sys.executable, "-c", "import time; time.sleep(30)"]
    assert fetch_pdf.pdf_text(b"%PDF-1.4", seconds=0.5, command=slow) is None
    assert time.perf_counter() - started < 5


def test_a_long_pdf_is_cut_around_the_claim():
    pages = [("Filler about harbour fees and parking. " * 30) for _ in range(12)]
    pages[9] = "Restored salt marsh cut flood damage by a third in every council that tried it."
    page = read("https://gov.example.org/r", {("gov.example.org", "/r"): pdf_reply(make_pdf(pages))},
                about="salt marsh flood damage")
    assert page.status == "ok" and len(page.text) <= MAX_CHARS
    assert "Restored salt marsh cut flood damage" in page.text


def test_a_redirect_to_a_private_address_is_refused():
    routes = {("gov.example.org", "/r.pdf"): (302, {"location": "http://127.0.0.1/r.pdf"}, b"")}
    page = read("https://gov.example.org/r.pdf", routes)
    assert page.status == "unread" and page.reason == "address"


def test_a_pdf_link_asks_for_pdfs():
    seen = []
    fetch("https://gov.example.org/r", resolver=resolver({}),
          transport=serving({("gov.example.org", "/r"): pdf_reply((PDFS / "flood_report.pdf").read_bytes())}, seen))
    assert "application/pdf" in seen[0].headers["accept"]


@pytest.mark.parametrize("url,paper", [
    ("https://arxiv.org/abs/1706.03762", "https://arxiv.org/pdf/1706.03762"),
    ("https://arxiv.org/abs/1706.03762v7", "https://arxiv.org/pdf/1706.03762v7"),
    ("http://www.arxiv.org/abs/cs/0101001", "https://arxiv.org/pdf/cs/0101001"),
    ("https://arxiv.org/abs/1706.03762?context=cs", "https://arxiv.org/pdf/1706.03762"),
    ("https://arxiv.org/pdf/1706.03762", None),
    ("https://example.org/abs/1706.03762", None),
    ("https://arxiv.org/list/cs.AI/recent", None),
])
def test_the_full_paper_behind_an_arxiv_abstract(url, paper):
    assert fetch_pdf.arxiv_paper(url) == paper


@pytest.mark.parametrize("url,research", [
    ("https://arxiv.org/abs/1706.03762", True), ("https://arxiv.org/pdf/1706.03762v2", True),
    ("https://export.arxiv.org/abs/1706.03762", True), ("https://arxiv.org/list/cs.AI/recent", False),
    ("https://notarxiv.org/abs/1706.03762", False),
])
def test_arxiv_papers_are_research(url, research):
    assert fetch_pdf.is_arxiv_paper(url) is research
