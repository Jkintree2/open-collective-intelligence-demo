"""The page reader: public addresses only (checked on every redirect), small, text only. No network."""

from pathlib import Path

import httpx
import pytest

from app import fetch_page
from app.fetch_page import Refused, checked_target, cut, fetch, html_text, iso_date

PAGES = Path(__file__).parent / "fixtures" / "pages"
PUBLIC = "93.184.216.34"


def resolver(table):
    def resolve(host, port):
        return table.get(host, [PUBLIC])
    return resolve


def serving(routes, seen=None):
    """A transport answering by (Host header, path); records each request."""
    def respond(request):
        if seen is not None:
            seen.append(request)
        key = (request.headers["host"], request.url.path)
        status, headers, body = routes.get(key, (404, {}, b""))
        return httpx.Response(status, headers=headers, content=body)
    return httpx.MockTransport(respond)


def html(name):
    return (200, {"content-type": "text/html; charset=utf-8"}, (PAGES / name).read_bytes())


@pytest.mark.parametrize("url", [
    "http://localhost/", "http://127.0.0.1/", "http://10.0.0.5/", "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://[fd00::1]/",
    "http://[::ffff:127.0.0.1]/", "http://0.0.0.0/", "http://printer.local/",
    "ftp://example.org/", "file:///etc/passwd", "http://user:pw@example.org/",
    "http://example.org:22/", "javascript:alert(1)", "http:///nohost",
])
def test_refuses_private_local_and_odd_addresses(url):
    with pytest.raises(Refused):
        checked_target(url, resolver({}))


def test_refuses_a_name_that_resolves_to_a_private_address():
    with pytest.raises(Refused):
        checked_target("https://intranet.example.org/", resolver({"intranet.example.org": ["10.1.2.3"]}))
    with pytest.raises(Refused):
        checked_target("https://mixed.example.org/", resolver({"mixed.example.org": [PUBLIC, "127.0.0.1"]}))


def test_connects_to_the_checked_address_and_keeps_the_name():
    target, host, tls = checked_target("https://news.example.org/a?b=1#frag", resolver({}))
    assert target == f"https://{PUBLIC}/a?b=1" and host == "news.example.org" and tls == "news.example.org"


def test_reads_an_article_and_drops_scripts_menus_and_footers():
    seen = []
    page = fetch("https://news.example.org/story", resolver=resolver({}),
                 transport=serving({("news.example.org", "/story"): html("news_article.html")}, seen))
    assert page.status == "ok"
    assert "number of flooding days has doubled since 2000" in page.text
    for gone in ("do not keep this", "color: red", "Subscribe now", "ten recipes", "Copyright"):
        assert gone not in page.text
    assert page.title == "Coastal towns see record flooding | Example News"
    assert page.description.startswith("A survey of forty towns")
    assert page.published == "2024-03-14"
    assert seen[0].url.host == PUBLIC and seen[0].extensions["sni_hostname"] == "news.example.org"


def test_date_from_structured_data():
    text, title, _, published = html_text((PAGES / "research_ld.html").read_text())
    assert published == "2021-07" and title == "Sea level rise and urban flooding"
    assert "tide gauge records" in text and "ScholarlyArticle" not in text


def test_a_redirect_to_a_private_address_is_refused():
    routes = {("short.example.org", "/x"): (302, {"location": "http://inside.example.org/admin"}, b"")}
    page = fetch("https://short.example.org/x", resolver=resolver({"inside.example.org": ["192.168.0.10"]}),
                 transport=serving(routes))
    assert page.status == "unread" and page.reason == "address"


def test_follows_at_most_three_redirects():
    routes = {("a.example.org", f"/{i}"): (301, {"location": f"/{i + 1}"}, b"") for i in range(5)}
    routes[("a.example.org", "/3")] = html("news_article.html")
    assert fetch("https://a.example.org/0", resolver=resolver({}), transport=serving(routes)).status == "ok"
    routes[("a.example.org", "/3")] = (301, {"location": "/4"}, b"")
    routes[("a.example.org", "/4")] = html("news_article.html")
    page = fetch("https://a.example.org/0", resolver=resolver({}), transport=serving(routes))
    assert page.status == "unread" and page.reason == "redirects"


@pytest.mark.parametrize("url,content_type", [
    ("https://example.org/report.pdf", None),
    ("https://www.youtube.com/watch?v=abc", None),
    ("https://example.org/file", "application/pdf"),
    ("https://example.org/pic", "image/png"),
])
def test_links_that_are_not_web_pages_are_unsupported(url, content_type):
    seen = []
    routes = {("example.org", "/file"): (200, {"content-type": content_type or ""}, b"%PDF"),
              ("example.org", "/pic"): (200, {"content-type": content_type or ""}, b"\x89PNG")}
    page = fetch(url, resolver=resolver({}), transport=serving(routes, seen))
    assert page.status == "unsupported"
    if content_type is None:
        assert seen == []


def test_a_large_page_is_cut_and_never_read_past_two_megabytes(monkeypatch):
    monkeypatch.setattr(fetch_page, "MAX_BYTES", 5000)
    body = ("<p>" + "filler words here " * 50 + "</p>") * 200
    routes = {("big.example.org", "/"): (200, {"content-type": "text/html"}, body.encode())}
    page = fetch("https://big.example.org/", resolver=resolver({}), transport=serving(routes))
    assert page.status == "ok" and len(page.text) <= 5000


@pytest.mark.parametrize("status,reason", [(404, "http"), (500, "http")])
def test_errors_and_empty_pages_are_unread(status, reason):
    routes = {("e.example.org", "/"): (status, {"content-type": "text/html"}, b"<p>gone</p>"),
              ("e.example.org", "/empty"): (200, {"content-type": "text/html"}, b"<script>app()</script>")}
    assert fetch("https://e.example.org/", resolver=resolver({}), transport=serving(routes)).reason == reason
    empty = fetch("https://e.example.org/empty", resolver=resolver({}), transport=serving(routes))
    assert empty.status == "unread" and empty.reason == "empty"


def test_timeouts_and_network_failures_are_unread():
    def slow(request):
        raise httpx.ReadTimeout("slow")

    def down(request):
        raise httpx.ConnectError("down")

    assert fetch("https://x.example.org/", resolver=resolver({}), transport=httpx.MockTransport(slow)).reason == "timeout"
    assert fetch("https://x.example.org/", resolver=resolver({}), transport=httpx.MockTransport(down)).reason == "network"


def test_plain_text_and_charset():
    routes = {("t.example.org", "/"): (200, {"content-type": "text/plain; charset=latin-1"},
                                      "Café owners say the flood reached the counter twice this year.".encode("latin-1"))}
    page = fetch("https://t.example.org/", resolver=resolver({}), transport=serving(routes))
    assert page.status == "ok" and page.text.startswith("Café owners")


def test_cut_keeps_the_part_about_the_claim():
    text = "\n".join(["unrelated sport results and weather"] * 400 + ["sea walls fail against rising flooding"] + ["more sport"] * 400)
    kept = cut(text, "Sea walls and flooding", limit=2000)
    assert len(kept) <= 2000 and "sea walls fail against rising flooding" in kept


@pytest.mark.parametrize("value,expected", [
    ("2024-03-14T08:00:00Z", "2024-03-14"), ("2021-07", "2021-07"), ("1999", "1999"),
    ("March 2024", None), (None, None), ("0001-01-01", None),
])
def test_iso_date(value, expected):
    assert iso_date(value) == expected


def test_the_log_line_holds_no_page_text(caplog):
    caplog.set_level("INFO", logger="oci")
    fetch("https://news.example.org/story", request_id="r1", resolver=resolver({}),
          transport=serving({("news.example.org", "/story"): html("news_article.html")}))
    assert "flooding days" not in caplog.text and '"host": "news.example.org"' in caplog.text
