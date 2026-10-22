"""PDFs behind evidence links: read by content type, size, page and time limits, no text, arXiv. No network."""

import gzip
import json
import subprocess
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


def test_the_limits_are_fifteen_megabytes_forty_pages_and_twenty_five_seconds():
    # 25 seconds: on Render's tenth of a CPU a 15 page arXiv paper takes about 20.
    assert fetch_pdf.MAX_BYTES == 15_000_000 and fetch_pdf.MAX_PAGES == 40 and fetch_pdf.READ_SECONDS == 25


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


class FakeResource:
    RLIMIT_AS, RLIM_INFINITY = 9, -1

    def __init__(self, hard=-1):
        self.hard, self.set = hard, None

    def getrlimit(self, which):
        return (self.hard, self.hard)

    def setrlimit(self, which, limits):
        self.set = (which, limits)


@pytest.mark.parametrize("hard,soft", [(-1, fetch_pdf.MEMORY_BYTES), (100_000_000, 100_000_000)])
def test_the_reading_process_caps_its_memory_on_linux(monkeypatch, hard, soft):
    fake = FakeResource(hard)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "resource", fake)
    assert fetch_pdf.cap_memory() is True
    assert fake.set == (FakeResource.RLIMIT_AS, (soft, hard))


def test_no_memory_cap_where_the_system_does_not_enforce_one(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert fetch_pdf.cap_memory() is False


def test_the_reading_process_sets_the_cap_when_it_can():
    probe = ("import resource, sys; from app.fetch_pdf import cap_memory, MEMORY_BYTES; "
             "print(cap_memory(), resource.getrlimit(resource.RLIMIT_AS)[0] == MEMORY_BYTES)")
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd=fetch_pdf.ROOT, check=True)
    assert done.stdout.split() == (["True", "True"] if sys.platform.startswith("linux") else ["False", "False"])


def slow_reader(*pages, cut_off=""):
    """A reader process that sends a title line and `pages`, then a line cut off part way, then hangs."""
    lines = [json.dumps({"title": "Slow report", "published": "2024-06-11"})] + [json.dumps({"page": p}) for p in pages]
    script = ("import sys, time; sys.stdin.buffer.read(); "
              f"sys.stdout.write({chr(10).join(lines) + chr(10)!r} + {cut_off!r}); sys.stdout.flush(); time.sleep(30)")
    return [sys.executable, "-c", script]


SLOW_PAGES = ("Councils that restored salt marsh saw flood damage fall by a third over five years.",
              "Sea walls alone did not reduce flood damage over the same period in any council.")


def test_a_reading_out_of_time_keeps_the_pages_read_so_far(monkeypatch):
    monkeypatch.setattr(fetch_pdf, "READ_SECONDS", 1.5)
    monkeypatch.setattr(fetch_pdf, "READER", slow_reader(*SLOW_PAGES, cut_off='{"page": "Third page never fini'))
    started = time.perf_counter()
    found = fetch_pdf.pdf_text(b"%PDF-1.4")
    assert time.perf_counter() - started < 5
    assert found.partial and found.pages == 2 and found.title == "Slow report"
    assert "Third page" not in found.text
    page = read("https://gov.example.org/r", {("gov.example.org", "/r"): pdf_reply(b"%PDF-1.4 slow")})
    assert page.status == "ok" and page.title == "Slow report" and page.published == "2024-06-11"
    assert SLOW_PAGES[0] in page.text and SLOW_PAGES[1] in page.text


def test_a_reading_out_of_time_before_any_page_is_unread(monkeypatch):
    monkeypatch.setattr(fetch_pdf, "READ_SECONDS", 1.5)
    monkeypatch.setattr(fetch_pdf, "READER", slow_reader())
    assert fetch_pdf.pdf_text(b"%PDF-1.4") is None
    page = read("https://gov.example.org/r", {("gov.example.org", "/r"): pdf_reply(b"%PDF-1.4 slow")})
    assert page.status == "unread" and page.reason == "pdf"


def test_a_reading_out_of_time_with_only_blank_pages_is_unread_not_scanned(monkeypatch):
    monkeypatch.setattr(fetch_pdf, "READ_SECONDS", 1.5)
    monkeypatch.setattr(fetch_pdf, "READER", slow_reader("", " "))
    page = read("https://gov.example.org/r", {("gov.example.org", "/r"): pdf_reply(b"%PDF-1.4 slow")})
    assert page.status == "unread" and page.reason == "pdf"


def test_a_whole_reading_is_not_partial():
    found = fetch_pdf.pdf_text((PDFS / "flood_report.pdf").read_bytes())
    assert not found.partial and found.pages == 2 and "salt marsh" in found.text
