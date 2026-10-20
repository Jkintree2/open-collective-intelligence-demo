"""The page reader: public addresses only (checked on every redirect), small, text only. No network."""

import gzip
import json
import logging
import zlib
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
        # A stream, as from the network: the reader takes the bytes as they were sent.
        return httpx.Response(status, headers=headers, stream=httpx.ByteStream(body))
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
    text, title, _, published, _ = html_text((PAGES / "research_ld.html").read_text())
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


def test_a_compressed_page_is_read(monkeypatch):
    words = ("<p>" + "The harbour wall kept the old town dry all winter. " * 20 + "</p>").encode()
    for encoding, body in (("gzip", gzip.compress(words)), ("deflate", zlib.compress(words)),
                           ("deflate", zlib.compress(words)[2:-4])):
        routes = {("z.example.org", "/"): (200, {"content-type": "text/html", "content-encoding": encoding}, body)}
        page = fetch("https://z.example.org/", resolver=resolver({}), transport=serving(routes))
        assert page.status == "ok" and "harbour wall" in page.text, encoding


def test_a_compressed_page_is_never_unpacked_past_two_megabytes(monkeypatch, caplog):
    monkeypatch.setattr(fetch_page, "MAX_BYTES", 5000)
    bomb = gzip.compress(b"flood " * 4_000_000)  # 24 MB unpacked, about 25 KB sent
    routes = {("bomb.example.org", "/"): (200, {"content-type": "text/plain", "content-encoding": "gzip"}, bomb)}
    with caplog.at_level(logging.INFO, logger="oci"):
        page = fetch("https://bomb.example.org/", resolver=resolver({}), transport=serving(routes))
    assert page.status == "ok" and len(page.text) <= 5000
    entry = json.loads(next(r.message for r in caplog.records if '"event": "fetch"' in r.message))
    assert entry["bytes"] <= 5001  # one byte past the limit says the page was longer; never the 24 MB


def test_an_encoding_the_reader_cannot_unpack_is_unread():
    routes = {("br.example.org", "/"): (200, {"content-type": "text/html", "content-encoding": "br"}, b"\x1b\x00")}
    page = fetch("https://br.example.org/", resolver=resolver({}), transport=serving(routes))
    assert (page.status, page.reason) == ("unread", "encoding")


def test_the_reader_asks_only_for_encodings_it_can_unpack():
    seen = []
    fetch("https://x.example.org/", resolver=resolver({}), transport=serving({}, seen))
    assert seen[0].headers["accept-encoding"] == "gzip, deflate"


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


def test_navigation_blocks_marked_by_role_or_class_are_dropped():
    page = ('<div id="content"><p>The Earth is an oblate spheroid, as measured since antiquity.</p>'
            '<div role="navigation"><ul><li>Flat Earth</li><li><br>Pseudoscience</li></ul></div>'
            '<div class="navbox"><table><tr><td>Flat Earth societies</td></tr></table></div>'
            '<p hidden>secret</p><img src="x"><p>Closing remark.</p></div>')
    text = html_text(page)[0]
    assert "oblate spheroid" in text and "Closing remark" in text
    for gone in ("Pseudoscience", "societies", "secret"):
        assert gone not in text


def test_cut_keeps_the_opening_of_a_long_page():
    text = "\n".join(["The page opens with its own summary of the matter."] + ["filler about sport"] * 2000
                     + ["sea walls fail against rising flooding"])
    kept = cut(text, "Sea walls and flooding", limit=3000)
    assert kept.startswith("The page opens") and "sea walls fail" in kept and len(kept) <= 3000


def test_backup_reader_turns_markdown_into_a_page_and_keeps_the_key_out_of_logs(caplog):
    from app.config import Settings
    from app.fetch_page import backup_fetch
    caplog.set_level("INFO", logger="oci")
    settings = Settings("t", "t", "t", "neo4j://x", "n", "p", llm_api_key="private-test-key")
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"title": "Story", "content":
            "# Story\n\n![chart](https://x/c.png)\nA [survey](https://x/s) of **forty** towns found flooding days doubled\\. Not a service\\; really\\."})

    page = backup_fetch("https://blocked.example.org/a", settings, transport=httpx.MockTransport(respond))
    assert page.status == "ok" and page.title == "Story"
    assert "A survey of forty towns found flooding days doubled. Not a service; really." in page.text and "chart" not in page.text
    assert str(seen[0].url) == "https://api.deepseek.com/v1/tools/fetch"
    assert seen[0].headers["authorization"] == "Bearer private-test-key"
    assert "private-test-key" not in caplog.text and '"reader": "deepseek"' in caplog.text


@pytest.mark.parametrize("status", [404, 403, 429, 500])
def test_backup_reader_failures_are_unread(status):
    from app.config import Settings
    from app.fetch_page import backup_fetch
    settings = Settings("t", "t", "t", "neo4j://x", "n", "p", llm_api_key="k")
    page = backup_fetch("https://x.example.org/", settings,
                        transport=httpx.MockTransport(lambda request: httpx.Response(status, json={"error": {}})))
    assert page.status == "unread"


def test_backup_is_never_asked_about_a_refused_address():
    from app.config import Settings
    from app.fetch_page import Page, backup_allowed
    settings = Settings("t", "t", "t", "neo4j://x", "n", "p", llm_api_key="k")
    assert backup_allowed(Page("unread", "u", reason="http"), settings)
    for reason in ("address", "scheme", "malformed", "dns"):
        assert not backup_allowed(Page("unread", "u", reason=reason), settings)
    assert not backup_allowed(Page("unsupported", "u", reason="type"), settings)


def test_last_updated_date_is_kept_beside_the_first_published_one():
    page = ('<script type="application/ld+json">{"datePublished":"2001-12-06T15:55:52Z",'
            '"dateModified":"2026-10-17T13:53:58Z"}</script><p>Flat Earth is a disproven idea about the shape of Earth.</p>')
    assert html_text(page)[3:] == ("2001-12-06", "2026-10-17")
    meta = '<meta property="article:modified_time" content="2025-02-01"><p>text</p>'
    assert html_text(meta)[4] == "2025-02-01"
