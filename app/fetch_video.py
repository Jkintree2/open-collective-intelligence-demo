"""Phase 2: the captions of a YouTube video behind an evidence link, or a transcript the writer pasted; no Cypher.

YouTube has no official free way to read another channel's captions, so this is best effort
(03_schema.md, revision round: YouTube videos). The caption track is found through YouTube's player data
as its Android app asks for it; the title, channel and upload date through the same data as the website
asks for it. Every request goes to a public address checked and pinned as for pages, follows no redirect,
and stops at MAX_BYTES and TIMEOUT_S. A pasted transcript is never logged or kept.
"""

from __future__ import annotations

import bisect
import html
import json
import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import httpx

from app.fetch_page import (MAX_BYTES, TIMEOUT_S, Page, Refused, Resolver, _Body, _Encoding, checked_target, cut,
                            iso_date, resolve, tidy)

log = logging.getLogger("oci")

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
WATCH_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
PLAYER = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"
# The player data as YouTube's Android app asks for it carries caption tracks that open without the
# website's player token; as the website asks for it, it carries the upload date.
ANDROID = ({"clientName": "ANDROID", "clientVersion": "20.10.38", "androidSdkVersion": 30, "hl": "en"},
           "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip")
WEB = ({"clientName": "WEB", "clientVersion": "2.20250312.04.00", "hl": "en"},
       "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TOTAL_SECONDS = 20
MAX_TRANSCRIPT = 60_000
PARAGRAPH = 600
# A government channel is an organisation; any other kind the reading guesses is other (03_schema.md).
CHANNEL_TYPES = {"news": "news", "organisation": "organisation", "government": "organisation"}


@dataclass
class Video(Page):
    """A Page whose text came from captions or a paste; `segments` keep each piece's start in seconds
    (None when a paste gave no times), for the quote's time."""
    segments: list[tuple[str, float | None]] = field(default_factory=list)


class _Failed(Exception):
    """outcome: refused (YouTube said no), error (network, time, size) or no_captions."""


def video_id(url: str) -> str | None:
    """The video behind a youtube.com/watch, m.youtube.com/watch, youtube.com/shorts or youtu.be link."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https"):
        return None
    if host == "youtu.be":
        found = parts.path.strip("/")
    elif host in WATCH_HOSTS and parts.path.rstrip("/") == "/watch":
        found = (parse_qs(parts.query).get("v") or [""])[0]
    elif host in WATCH_HOSTS and parts.path.startswith("/shorts/"):
        found = parts.path[len("/shorts/"):].strip("/")
    else:
        return None
    return found if VIDEO_ID.match(found) else None


def is_video(url: str | None) -> bool:
    return bool(url) and video_id(url) is not None


def clock(seconds: float) -> str:
    """'4:12' or '1:02:03'."""
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def quote_time(quote: str | None, segments: list[tuple[str, float | None]]) -> str | None:
    """Where `quote` starts in the video, from the segment it begins in; None when there is no time."""
    from app.check import flat  # here, not at the top: app.check reads pages through app.fetch_page

    wanted = flat(quote or "").strip(" .\"'")
    if len(wanted) < 12 or not segments:
        return None
    starts, joined, size = [], [], 0
    for text, _ in segments:
        piece = flat(text)
        starts.append(size)
        joined.append(piece)
        size += len(piece) + 1
    at = " ".join(joined).find(wanted)
    if at < 0:
        return None
    seconds = segments[bisect.bisect_right(starts, at) - 1][1]
    return clock(seconds) if seconds is not None else None


def channel_source(source: dict | None) -> dict | None:
    """A video's source facts: the type says what the channel is (news, organisation or other)."""
    if not source:
        return source
    return {**source, "type": CHANNEL_TYPES.get(source.get("type") or "", "other")}


def caption_segments(xml: str) -> list[tuple[str, float | None]]:
    """(text, start in seconds) from a caption track, in YouTube's format 3 (<p t="ms">) or its older
    one (<text start="s">). Read with patterns, not an XML parser, so nothing in the file is expanded."""
    found = [(text, int(t) / 1000) for t, text in re.findall(r'<p\b[^>]*?\bt="(\d+)"[^>]*>(.*?)</p>', xml, re.S)]
    if not found:
        found = [(text, float(t)) for t, text in
                 re.findall(r'<text\b[^>]*?\bstart="(\d+(?:\.\d+)?)"[^>]*>(.*?)</text>', xml, re.S)]
    out = []
    for text, start in found:
        text = " ".join(html.unescape(html.unescape(re.sub(r"<[^>]+>", " ", text))).split())
        if text:
            out.append((text, start))
    return out


STAMP = re.compile(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:\s+(.*))?$")
SPOKEN_TIME = re.compile(r"^\d+ (?:hours?|minutes?|seconds?)(?:,? \d+ (?:minutes?|seconds?))*$", re.I)


def pasted_segments(text: str) -> list[tuple[str, float | None]]:
    """(text, start) from a pasted transcript. A time on its own line or at the start of one ("4:12", as
    YouTube's "Show transcript" gives them) dates the words after it and is not itself read."""
    out, start = [], None
    for line in text[:MAX_TRANSCRIPT].splitlines():
        line = " ".join(line.split())
        if not line or SPOKEN_TIME.match(line):
            continue
        if match := STAMP.match(line):
            hours, minutes, secs, rest = match.groups()
            start = int(hours or 0) * 3600 + int(minutes) * 60 + int(secs)
            if not rest:
                continue
            line = rest
        out.append((line, start))
    return out


def segments_text(segments: list[tuple[str, float | None]]) -> str:
    """The words as paragraphs of about PARAGRAPH characters, for cut() and the reading."""
    paragraphs, current = [], []
    for text, _ in segments:
        current.append(text)
        if sum(len(t) + 1 for t in current) >= PARAGRAPH:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return tidy("\n".join(paragraphs))


def _get(client: httpx.Client, url: str, resolver: Resolver, agent: str, deadline: float,
         body: dict | None = None) -> bytes:
    try:
        target, host_header, tls_name = checked_target(url, resolver)
    except Refused as exc:
        raise _Failed("refused") from exc
    if not (tls_name == "youtube.com" or tls_name.endswith(".youtube.com")):
        raise _Failed("refused")
    request = client.build_request("POST" if body is not None else "GET", target, json=body, headers={
        "Host": host_header, "User-Agent": agent, "Accept-Encoding": "gzip, deflate", "Accept-Language": "en"},
        extensions={"sni_hostname": tls_name})
    try:
        response = client.send(request, stream=True)
    except httpx.HTTPError as exc:
        raise _Failed("error") from exc
    try:
        if response.is_redirect or response.status_code in (401, 403, 429):
            raise _Failed("refused")
        if response.is_error:
            raise _Failed("error")
        data = _Body(response.headers.get("content-encoding", ""))
        for chunk in response.iter_raw():
            if not data.add(chunk) or time.perf_counter() > deadline:
                raise _Failed("error")
    except (_Encoding, httpx.HTTPError) as exc:
        raise _Failed("error") from exc
    finally:
        response.close()
    return bytes(data.data)


def _player(client, vid, who, resolver, deadline) -> dict:
    context, agent = who
    raw = _get(client, PLAYER, resolver, agent, deadline, body={"context": {"client": context}, "videoId": vid})
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise _Failed("error") from exc
    if not isinstance(data, dict):
        raise _Failed("error")
    return data


def _track(tracks: list) -> str | None:
    """A track the video's owner wrote before an automatic one, English before other languages."""
    usable = [t for t in tracks if isinstance(t, dict) and isinstance(t.get("baseUrl"), str)]
    english = lambda t: str(t.get("languageCode", "")).lower().startswith("en")  # noqa: E731
    written = lambda t: t.get("kind") != "asr"  # noqa: E731
    for wanted in (lambda t: written(t) and english(t), english, written, lambda t: True):
        if chosen := next((t for t in usable if wanted(t)), None):
            return chosen["baseUrl"]
    return None


def _about(details: dict, micro: dict) -> tuple[str | None, str | None, str | None]:
    """(title, description for the reading, upload date) from the player data."""
    title = (details.get("title") or micro.get("title", {}).get("simpleText") or "").strip() or None
    channel = (details.get("author") or micro.get("ownerChannelName") or "").strip()
    words = [f"A YouTube video by {channel}." if channel else "A YouTube video."]
    if micro.get("category"):
        words.append(f"Category: {micro['category']}.")
    if details.get("shortDescription"):
        words.append(" ".join(str(details["shortDescription"]).split())[:600])
    return title, " ".join(words), iso_date(micro.get("uploadDate") or micro.get("publishDate"))


def _read(url: str, about: str, transcript: str | None, resolver, transport, entry) -> Video:
    vid = video_id(url)
    deadline = time.perf_counter() + TOTAL_SECONDS
    with httpx.Client(timeout=httpx.Timeout(TIMEOUT_S, connect=4), transport=transport,
                      follow_redirects=False, verify=True, trust_env=False) as client:
        android: dict = {}
        try:
            if transcript is None:
                android = _player(client, vid, ANDROID, resolver, deadline)
                if (android.get("playabilityStatus") or {}).get("status") not in ("OK", None):
                    raise _Failed("refused")
            # The upload date and category: best effort, a reading goes on without them.
            try:
                web = _player(client, vid, WEB, resolver, deadline)
            except _Failed:
                web = {}
            details = web.get("videoDetails") or android.get("videoDetails") or {}
            micro = (web.get("microformat") or {}).get("playerMicroformatRenderer") or {}
            title, description, published = _about(details, micro)
            if transcript is not None:
                entry["outcome"] = "pasted"
                segments = pasted_segments(transcript)
            else:
                tracks = (((android.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {})
                          .get("captionTracks") or [])
                base = _track(tracks)
                if base is None:
                    raise _Failed("no_captions")
                segments = caption_segments(_get(client, base, resolver, ANDROID[1], deadline).decode("utf-8", "replace"))
                entry["outcome"] = "ok"
        except _Failed as exc:
            entry["outcome"] = str(exc)
            return Video("unread", url, reason=str(exc))
    entry["segments"] = len(segments)
    if transcript is None and len(segments_text(segments)) < 40:
        entry["outcome"] = "no_captions"
    return video_page(url, segments, about, title, description, published)


def video_page(url: str, segments: list[tuple[str, float | None]], about: str = "", title: str | None = None,
               description: str | None = None, published: str | None = None) -> Video:
    """The Page for captions or a paste: its words cut around `about`, as a page's are."""
    text = segments_text(segments)
    if len(text) < 40:
        return Video("unread", url, reason="no_captions", title=title)
    return Video("ok", url, cut(text, about), title, description, published, segments=segments)


def fetch(url: str, *, about: str = "", request_id: str | None = None, transcript: str | None = None,
          resolver: Resolver = resolve, transport: httpx.BaseTransport | None = None, **_) -> Video:
    """The captions of the video behind `url` (or `transcript`, the writer's paste) as a Page, cut around
    `about`. Never raises; logs the reader and its outcome, never the text."""
    started = time.perf_counter()
    entry = {"event": "fetch", "request_id": request_id, "reader": "youtube"}
    page = _read(url, about, transcript, resolver, transport, entry)
    entry.update(status=page.status, chars=len(page.text), ms=round((time.perf_counter() - started) * 1000))
    log.info(json.dumps(entry))
    return page
