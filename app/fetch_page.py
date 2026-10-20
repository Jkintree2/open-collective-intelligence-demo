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
from dataclasses import dataclass
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
NOT_PAGES = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|zip|gz|mp[34]|m4a|mov|avi|webm|wav|ogg|png|jpe?g|gif|webp|svg)$", re.I)
VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com")
USER_AGENT = "OpenCollectiveIntelligence/0.2 (reads one page a person cited)"

Resolver = Callable[[str, int], list[str]]


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


class Refused(Exception):
    pass


def resolve(host: str, port: int) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
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
    host = parts.hostname.rstrip(".").lower()
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
    host_header = parts.netloc.rsplit("@", 1)[-1]
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


def html_text(html: str) -> tuple[str, str | None, str | None, str | None]:
    """(text, title, description, published) from an HTML page; scripts, menus and footers dropped."""
    parser = _Text()
    parser.feed(html)
    parser.close()
    published = parser.published
    if not published and parser.ld:
        match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', parser.ld)
        published = match.group(1) if match else None
    return tidy("".join(parser.parts)), (tidy(parser.title) or None), parser.description, iso_date(published)


def tidy(text: str) -> str:
    lines = (re.sub(r"[ \t\r\f\v ]+", " ", line).strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def iso_date(value: str | None) -> str | None:
    """YYYY-MM-DD, YYYY-MM or YYYY from the start of a date string; None when there is none."""
    match = re.match(r"\s*(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value or "")
    if not match or not 1900 <= int(match.group(1)) <= 2100:
        return None
    return "-".join(part for part in match.groups() if part)


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


def fetch(url: str, *, about: str = "", request_id: str | None = None,
          resolver: Resolver = resolve, transport: httpx.BaseTransport | None = None) -> Page:
    """The page behind `url`, cut to MAX_CHARS around `about`. Never raises for a bad page."""
    started = time.perf_counter()
    entry = {"event": "fetch", "request_id": request_id, "reader": "site"}
    page = _fetch(url, about, resolver, transport, entry, started)
    entry.update(status=page.status, reason=page.reason, chars=len(page.text),
                 ms=round((time.perf_counter() - started) * 1000))
    log.info(json.dumps(entry))
    if page.text:
        log.debug(json.dumps({"event": "fetch_text", "request_id": request_id, "text": page.text[:2000]}))
    return page


def _fetch(url, about, resolver, transport, entry, started) -> Page:
    if unsupported(url):
        return Page("unsupported", url, reason="type")
    current = url
    with httpx.Client(timeout=httpx.Timeout(TIMEOUT_S, connect=4), transport=transport,
                      follow_redirects=False, verify=True) as client:
        for hop in range(MAX_REDIRECTS + 1):
            try:
                target, host_header, tls_name = checked_target(current, resolver)
            except Refused as exc:
                return Page("unread", current, reason=str(exc))
            entry["host"] = tls_name
            request = client.build_request("GET", target, headers={
                "Host": host_header, "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9"},
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
                if not content_type.startswith(TEXT_TYPES):
                    return Page("unsupported", current, reason="type")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES or time.perf_counter() - started > TIMEOUT_S * 2:
                        break
            except httpx.HTTPError:
                return Page("unread", current, reason="network")
            finally:
                response.close()
            entry["bytes"] = len(body)
            raw = bytes(body[:MAX_BYTES]).decode(_charset(content_type, bytes(body[:4096])), "replace")
            if content_type.startswith("text/plain"):
                text, title, description, published = tidy(raw), None, None, None
            else:
                text, title, description, published = html_text(raw)
            if len(text) < 40:
                return Page("unread", current, reason="empty", title=title)
            return Page("ok", current, cut(text, about), title, description, published)
    return Page("unread", current, reason="redirects")
