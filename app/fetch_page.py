"""Read the page behind an evidence link: public addresses only, small, text only; no Cypher.

Every address is resolved and checked before connecting, and the connection goes to the
checked address (the host name travels in the Host header and TLS name), so a name that
resolves differently the second time cannot reach this machine or a private network.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import time
import zlib
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

log = logging.getLogger("oci")

TIMEOUT_S = 8
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3
MAX_CHARS = 12_000
PORTS = {None, 80, 443}
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
NOT_PAGES = re.compile(r"\.(docx?|xlsx?|pptx?|zip|gz|mp[34]|m4a|mov|avi|webm|wav|ogg|png|jpe?g|gif|webp|svg)$", re.I)
VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com")
USER_AGENT = "OpenCollectiveIntelligence/0.2 (reads one page a person cited)"


def user_agent(site_url: str | None = None) -> str:
    """Names the site, so a site that asks readers to say who they are (Wikipedia does) lets us in."""
    return f"OpenCollectiveIntelligence/0.2 (+{site_url}; reads one page a person cited)" if site_url else USER_AGENT

Resolver = Callable[[str, int], list[str]]
NAT64 = ipaddress.ip_network("64:ff9b::/96")
IPV4_COMPATIBLE = ipaddress.ip_network("::/96")


@dataclass
class Page:
    """status: ok, unread (could not open or read), or unsupported (not a web page)."""
    status: str
    url: str
    text: str = ""
    title: str | None = None
    description: str | None = None
    published: str | None = None
    reason: str = ""
    modified: str | None = None


class Refused(Exception):
    pass


def resolve(host: str, port: int) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        # Forms that carry an IPv4 address inside are judged by that address: mapped, NAT64 and the
        # old IPv4 compatible form.
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip in NAT64 or ip in IPV4_COMPATIBLE:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.is_global and not ip.is_multicast


def unsupported(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return bool(NOT_PAGES.search(parts.path)) or any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS)


def checked_target(url: str, resolver: Resolver) -> tuple[str, str, str]:
    """(url to connect to, Host header, TLS name) for a public http or https address, or Refused."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise Refused("malformed") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise Refused("scheme")
    if parts.username is not None or parts.password is not None or port not in PORTS:
        raise Refused("address")
    try:
        # A name in other letters travels in its ASCII form, as the Host header and TLS name need.
        host = httpx.URL(url).raw_host.decode("ascii").rstrip(".").lower()
    except (httpx.InvalidURL, UnicodeError) as exc:
        raise Refused("malformed") from exc
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise Refused("address")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses = resolver(host, port or (443 if parts.scheme == "https" else 80))
        except (OSError, UnicodeError) as exc:
            raise Refused("dns") from exc
    if not addresses or not all(public(a) for a in addresses):
        raise Refused("address")
    pinned = addresses[0]
    netloc = f"[{pinned}]" if ":" in pinned else pinned
    if port:
        netloc += f":{port}"
    host_header = (f"[{host}]" if ":" in host else host) + (f":{port}" if port else "")
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, "")), host_header, host


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "template",
            "iframe", "button", "select"}
    SKIP_ROLES = {"navigation", "banner", "contentinfo", "complementary", "search", "menu", "dialog"}
    SKIP_CLASSES = re.compile(r"\b(navbox|sidebar|catlinks|mw-jump|cookie|share|related|comments?)\b", re.I)
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article",
             "blockquote", "pre", "dd", "dt", "figcaption", "table", "ul", "ol", "main"}
    DATE_META = {"article:published_time", "datepublished", "date", "dc.date", "dc.date.issued",
                 "citation_publication_date", "citation_date", "pubdate", "publish-date", "og:published_time"}
    MODIFIED_META = {"article:modified_time", "og:updated_time", "datemodified", "last-modified", "dc.date.modified"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.skip = 0
        self.in_title = False
        self.in_ld = False
        self.title = ""
        self.description: str | None = None
        self.published: str | None = None
        self.modified: str | None = None
        self.ld = ""

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            name = (a.get("name") or a.get("property") or a.get("itemprop") or "").lower()
            content = a.get("content", "").strip()
            if name in ("description", "og:description") and content and not self.description:
                self.description = content
            elif name in self.DATE_META and content and not self.published:
                self.published = content
            elif name in self.MODIFIED_META and content and not self.modified:
                self.modified = content
        elif tag == "time" and a.get("datetime") and not self.published:
            self.published = a["datetime"]
        elif tag == "title":
            self.in_title = True
        elif tag == "script" and "ld+json" in a.get("type", ""):
            self.in_ld = True
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in self.VOID:
            return
        hidden = (tag in self.SKIP or a.get("role", "").lower() in self.SKIP_ROLES
                  or "hidden" in a or a.get("aria-hidden") == "true"
                  or bool(self.SKIP_CLASSES.search(a.get("class", "") + " " + a.get("id", ""))))
        self.stack.append((tag, hidden))
        self.skip += hidden

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script":
            self.in_ld = False
        if tag in self.BLOCK:
            self.parts.append("\n")
        if not any(open_tag == tag for open_tag, _ in self.stack):
            return
        while self.stack:
            open_tag, hidden = self.stack.pop()
            self.skip -= hidden
            if open_tag == tag:
                break

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif self.in_ld:
            self.ld += data
        elif not self.skip:
            self.parts.append(data)


def html_text(html: str) -> tuple[str, str | None, str | None, str | None, str | None]:
    """(text, title, description, published, modified) from an HTML page; scripts, menus and footers dropped."""
    parser = _Text()
    parser.feed(html)
    parser.close()
    published, modified = parser.published, parser.modified
    if parser.ld:
        if not published and (match := re.search(r'"datePublished"\s*:\s*"([^"]+)"', parser.ld)):
            published = match.group(1)
        if not modified and (match := re.search(r'"dateModified"\s*:\s*"([^"]+)"', parser.ld)):
            modified = match.group(1)
    return (tidy("".join(parser.parts)), (tidy(parser.title) or None), parser.description,
            iso_date(published), iso_date(modified))


def tidy(text: str) -> str:
    lines = (re.sub(r"[ \t\r\f\v ]+", " ", line).strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def iso_date(value: str | None) -> str | None:
    """YYYY-MM-DD, YYYY-MM or YYYY from the start of a date string; None when there is none."""
    match = re.match(r"\s*(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value or "")
    if not match or not 1900 <= int(match.group(1)) <= 2100:
        return None
    return "-".join(part for part in match.groups() if part)


def header_date(value: str | None) -> str | None:
    """YYYY-MM-DD from an HTTP date ("Tue, 20 Oct 2026 03:49:57 GMT"); None when there is none."""
    try:
        return iso_date(parsedate_to_datetime(value).date().isoformat()) if value else None
    except (TypeError, ValueError):
        return None


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower())}


def cut(text: str, about: str = "", limit: int = MAX_CHARS) -> str:
    """At most `limit` characters. A long page keeps its opening (a third) and then the stretch
    that shares most words with `about`, so both the page's own summary and the part about the
    claim reach the reading."""
    if len(text) <= limit:
        return text
    paragraphs = [p for p in text.split("\n") if p.strip()]
    lead, size = [], 0
    while paragraphs and size + len(paragraphs[0]) + 1 <= limit // 3:
        size += len(paragraphs[0]) + 1
        lead.append(paragraphs.pop(0))
    rest_limit = limit - size - 2
    wanted = words(about)
    if not wanted or not paragraphs:
        return ("\n".join(lead) + "\n\n" + "\n".join(paragraphs))[:limit]
    scores = [len(words(p) & wanted) for p in paragraphs]
    best = max(range(len(paragraphs)), key=lambda i: (scores[i], -i))
    start = best
    while start > 0 and sum(len(p) + 1 for p in paragraphs[start - 1:best + 1]) < rest_limit // 3:
        start -= 1
    return ("\n".join(lead) + "\n\n" + "\n".join(paragraphs[start:])[:rest_limit]).strip()[:limit]


def _charset(content_type: str, head: bytes) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.I) or re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', head, re.I)
    name = match.group(1) if match else "utf-8"
    name = name.decode("ascii", "ignore") if isinstance(name, bytes) else name
    try:
        "".encode(name)
        return name
    except LookupError:
        return "utf-8"


class _Encoding(Exception):
    pass


class _Body:
    """The page's bytes, unpacked here rather than by httpx so that a small compressed reply can never
    grow past MAX_BYTES in memory: each piece is unpacked only up to what is still allowed."""

    def __init__(self, encoding: str, limit: int | None = None) -> None:
        self.limit = limit or MAX_BYTES
        encoding = encoding.strip().lower()
        if encoding in ("", "identity"):
            self.unpack = None
        elif encoding in ("gzip", "x-gzip"):
            self.unpack = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif encoding == "deflate":
            self.unpack = zlib.decompressobj()
            self.raw_deflate = True  # some servers send deflate without its zlib header
        else:
            raise _Encoding(encoding)
        self.data = bytearray()

    def add(self, chunk: bytes) -> bool:
        """Adds a piece; False once the limit is reached."""
        if self.unpack is None:
            self.data += chunk[:self.limit + 1 - len(self.data)]
            return len(self.data) <= self.limit
        while chunk and len(self.data) <= self.limit:
            try:
                self.data += self.unpack.decompress(chunk, self.limit + 1 - len(self.data))
            except zlib.error as exc:
                if getattr(self, "raw_deflate", False) and not self.data:
                    self.raw_deflate = False
                    self.unpack = zlib.decompressobj(-zlib.MAX_WBITS)
                    continue
                raise _Encoding("bad data") from exc
            chunk = self.unpack.unconsumed_tail
        return len(self.data) <= self.limit


def fetch(url: str, *, about: str = "", request_id: str | None = None, agent: str = USER_AGENT,
          resolver: Resolver = resolve, transport: httpx.BaseTransport | None = None,
          transcript: str | None = None) -> Page:
    """The page behind `url`, cut to MAX_CHARS around `about`. Never raises for a bad page. A YouTube
    video goes to app/fetch_video.py (its captions, or `transcript`, the writer's paste)."""
    from app import fetch_video  # here, not at the top: fetch_video builds its Page from this module
    if fetch_video.is_video(url):
        return fetch_video.fetch(url, about=about, request_id=request_id, transcript=transcript,
                                 resolver=resolver, transport=transport)
    started = time.perf_counter()
    entry = {"event": "fetch", "request_id": request_id, "reader": "site"}
    page = _fetch(url, about, agent, resolver, transport, entry, started)
    entry.update(status=page.status, reason=page.reason, chars=len(page.text),
                 ms=round((time.perf_counter() - started) * 1000))
    log.info(json.dumps(entry))
    if page.text:
        log.debug(json.dumps({"event": "fetch_text", "request_id": request_id, "text": page.text[:2000]}))
    return page


def _fetch(url, about, agent, resolver, transport, entry, started) -> Page:
    from app import fetch_pdf  # here, not at the top: fetch_pdf builds its Page from this module
    if unsupported(url):
        return Page("unsupported", url, reason="type")
    current = url
    with httpx.Client(timeout=httpx.Timeout(TIMEOUT_S, connect=4), transport=transport,
                      follow_redirects=False, verify=True, trust_env=False) as client:
        for hop in range(MAX_REDIRECTS + 1):
            try:
                target, host_header, tls_name = checked_target(current, resolver)
            except Refused as exc:
                return Page("unread", current, reason=str(exc))
            entry["host"] = tls_name
            request = client.build_request("GET", target, headers={
                "Host": host_header, "User-Agent": agent,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,application/pdf;q=0.8",
                "Accept-Encoding": "gzip, deflate"},
                extensions={"sni_hostname": tls_name})
            try:
                response = client.send(request, stream=True)
            except httpx.TimeoutException:
                return Page("unread", current, reason="timeout")
            except httpx.HTTPError:
                return Page("unread", current, reason="network")
            try:
                entry["http"] = response.status_code
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location or hop == MAX_REDIRECTS:
                        return Page("unread", current, reason="redirects")
                    current = urljoin(current, location)
                    if unsupported(current):
                        return Page("unsupported", current, reason="type")
                    continue
                if response.is_error:
                    return Page("unread", current, reason="http")
                content_type = response.headers.get("content-type", "").lower()
                # A PDF, by content type, goes to app/fetch_pdf.py with its own size and time limits.
                pdf, stopped = fetch_pdf.is_pdf(content_type, current), None
                if not pdf and not content_type.startswith(TEXT_TYPES):
                    return Page("unsupported", current, reason="type")
                body = _Body(response.headers.get("content-encoding", ""), fetch_pdf.MAX_BYTES if pdf else None)
                for chunk in response.iter_raw():
                    if not body.add(chunk):
                        stopped = "too_big"
                    elif time.perf_counter() - started > (fetch_pdf.DOWNLOAD_SECONDS if pdf else TIMEOUT_S * 2):
                        stopped = "timeout"
                    if stopped:
                        break
            except _Encoding:
                return Page("unread", current, reason="encoding")
            except httpx.HTTPError:
                return Page("unread", current, reason="network")
            finally:
                response.close()
            entry["bytes"] = len(body.data)
            if pdf:
                entry["pdf"] = True
                return fetch_pdf.page(body.data, current, about, stopped)
            body = body.data
            raw = bytes(body[:MAX_BYTES]).decode(_charset(content_type, bytes(body[:4096])), "replace")
            if content_type.startswith("text/plain"):
                text, title, description, published, modified = tidy(raw), None, None, None, None
            else:
                text, title, description, published, modified = html_text(raw)
            if len(text) < 40:
                return Page("unread", current, reason="empty", title=title)
            # A page cut at MAX_BYTES can lose dates given at its end (Wikipedia's structured data on a long
            # article); the server's own last change date stands in for the page's.
            modified = modified or header_date(response.headers.get("last-modified"))
            return Page("ok", current, cut(text, about), title, description, published, modified=modified)
    return Page("unread", current, reason="redirects")


# X3: DeepSeek Fetch, the backup reader (api-docs.deepseek.com/guides/search; 0.75 USD per 1,000
# pages it returns, failures not billed). Only for a page our own reader could not open; never for
# an address the guard refused, which goes nowhere.
FETCH_PATH = "/v1/tools/fetch"
BACKUP_REASONS = {"timeout", "network", "http", "empty", "redirects"}


def markdown_text(markdown: str) -> str:
    """Plain sentences from Markdown: images dropped, links kept as their words, marks removed."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown)
    # Fetch escapes punctuation, commas included ("\,"); Markdown allows any ASCII mark to be escaped.
    text = re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+", "", text, flags=re.M)
    text = re.sub(r"(\*\*|__|`)", "", text)
    return tidy(text)


def backup_allowed(page: Page, settings) -> bool:
    return (page.status == "unread" and page.reason in BACKUP_REASONS and settings.deepseek_fetch
            and bool(settings.llm_api_key) and "deepseek" in settings.llm_base_url.lower())


def backup_fetch(url: str, settings, *, about: str = "", request_id: str | None = None,
                 transport: httpx.BaseTransport | None = None) -> Page:
    started = time.perf_counter()
    entry = {"event": "fetch", "request_id": request_id, "reader": "deepseek", "host": urlsplit(url).hostname}
    page = Page("unread", url, reason="backup")
    try:
        with httpx.Client(timeout=httpx.Timeout(15, connect=4), transport=transport) as client:
            response = client.post(settings.llm_base_url.rstrip("/") + FETCH_PATH, json={"url": url},
                                   headers={"Authorization": f"Bearer {settings.llm_api_key}"})
        entry["http"] = response.status_code
        if response.status_code == 200:
            data = response.json()
            text = markdown_text(data.get("content") or "") if isinstance(data, dict) else ""
            title = (data.get("title") or "").strip() or None if isinstance(data, dict) else None
            if len(text) >= 40:
                page = Page("ok", url, cut(text, about), title)
            else:
                page = Page("unread", url, reason="empty")
    except (httpx.HTTPError, ValueError):
        page = Page("unread", url, reason="backup")
    entry.update(status=page.status, chars=len(page.text), ms=round((time.perf_counter() - started) * 1000))
    log.info(json.dumps(entry))
    return page
