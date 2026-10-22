"""app/fetch_video.py: a YouTube video's captions, or a pasted transcript, read like a page. No network."""

import json
import logging
from pathlib import Path

import httpx
import pytest

from app import fetch_video
from app.fetch_page import fetch
from app.fetch_video import (caption_segments, channel_source, clock, is_video, pasted_segments, quote_time,
                             video_id)

VIDEOS = Path(__file__).parent / "fixtures" / "videos"
URL = "https://www.youtube.com/watch?v=AbCdEfGhIj0"
ANDROID = json.loads((VIDEOS / "player_android.json").read_text())
WEB = json.loads((VIDEOS / "player_web.json").read_text())
CAPTIONS = (VIDEOS / "captions.xml").read_text()
PASTED = (VIDEOS / "transcript.txt").read_text()


def public(host, port):
    return ["142.251.150.4"]


def reply(status=200, *, json_body=None, text=""):
    """A streamed reply, as YouTube sends one."""
    body = json.dumps(json_body).encode() if json_body is not None else text.encode()
    return httpx.Response(status, stream=httpx.ByteStream(body))


def youtube(seen, *, android=None, web=None, captions=CAPTIONS, status=None):
    """A stand in for YouTube: the player data for each client, and the caption track."""
    def respond(request):
        assert request.headers["host"] == "www.youtube.com" and request.url.host == "142.251.150.4"
        if request.url.path == "/youtubei/v1/player":
            client = json.loads(request.content)["context"]["client"]["clientName"]
            seen.append(client)
            if status:
                return reply(status)
            return reply(json_body=(android if android is not None else ANDROID) if client == "ANDROID"
                         else (web if web is not None else WEB))
        seen.append(str(request.url.params))
        return reply(text=captions)
    return httpx.MockTransport(respond)


def read(transport, url=URL, **kwargs):
    return fetch(url, about="pedestrian deaths fell", resolver=public, transport=transport, **kwargs)


@pytest.mark.parametrize("url, vid", [
    ("https://www.youtube.com/watch?v=AbCdEfGhIj0", "AbCdEfGhIj0"),
    ("https://youtube.com/watch?v=AbCdEfGhIj0&t=252s", "AbCdEfGhIj0"),
    ("https://m.youtube.com/watch?v=AbCdEfGhIj0", "AbCdEfGhIj0"),
    ("https://www.youtube.com/shorts/AbCd-fGh_j0", "AbCd-fGh_j0"),
    ("https://youtu.be/AbCdEfGhIj0?si=xyz", "AbCdEfGhIj0"),
    ("https://www.youtube.com/@LakeviewNews", None),
    ("https://www.youtube.com/playlist?list=PL123", None),
    ("https://www.youtube.com/watch?v=short", None),
    ("https://vimeo.com/76979871", None),
    ("https://www.tiktok.com/@someone/video/1234567890", None),
    ("javascript:alert(1)", None),
])
def test_which_links_are_videos(url, vid):
    assert video_id(url) == vid and is_video(url) is (vid is not None)


def test_captions_are_read_like_a_page(caplog):
    seen = []
    with caplog.at_level(logging.INFO, logger="oci"):
        page = read(youtube(seen))
    assert page.status == "ok" and page.title == "Lakeview lowered its speed limits. Here is what happened"
    assert page.description.startswith("A YouTube video by Lakeview Evening News. Category: News & Politics.")
    assert page.published == "2024-03-05"
    assert "pedestrian deaths in Lakeview fell by a third in the two years after the lower limit" in page.text
    assert "the city's own road safety figures" in page.text  # entities unpacked
    # The track the owner wrote, in English, before the automatic one and the French one.
    assert seen[:2] == ["ANDROID", "WEB"] and "written=1" in seen[2]
    entry = json.loads(next(r.message for r in caplog.records if '"reader": "youtube"' in r.message))
    assert entry["outcome"] == "ok" and entry["status"] == "ok" and entry["segments"] == 13 and "ms" in entry


def test_the_quote_carries_its_time():
    page = read(youtube([]))
    assert quote_time("The headline number: pedestrian deaths in Lakeview fell by a third", page.segments) == "4:12"
    # A sentence across two caption pieces starts in the first.
    assert quote_time("pedestrian deaths in Lakeview fell by a third in the two years after the lower limit, "
                      "from 18 to 12.", page.segments) == "4:12"
    assert quote_time("Deaths of drivers and passengers did not change in that time.", page.segments) == "4:37"
    assert quote_time("Something the video never says at all.", page.segments) is None
    assert quote_time("", page.segments) is None


def test_clock():
    assert clock(12.6) == "0:12" and clock(252) == "4:12" and clock(3723) == "1:02:03"


def test_a_video_with_no_captions():
    android = {**ANDROID, "captions": {}}
    page = read(youtube([], android=android))
    assert page.status == "unread" and page.reason == "no_captions"


def test_an_empty_caption_track_is_no_captions():
    assert read(youtube([], captions="")).reason == "no_captions"


@pytest.mark.parametrize("status", [403, 429])
def test_youtube_refusing_is_refused(status):
    assert read(youtube([], status=status)).reason == "refused"


def test_a_video_youtube_will_not_play_here_is_refused():
    android = {"playabilityStatus": {"status": "LOGIN_REQUIRED", "reason": "Sign in to confirm you're not a bot"}}
    assert read(youtube([], android=android)).reason == "refused"


def test_a_network_failure_is_an_error():
    def respond(request):
        raise httpx.ConnectError("down")
    assert read(httpx.MockTransport(respond)).reason == "error"


def test_a_redirect_is_not_followed():
    def respond(request):
        return httpx.Response(302, headers={"location": "http://10.0.0.1/"})
    assert read(httpx.MockTransport(respond)).reason == "refused"


def test_a_caption_track_on_another_host_is_not_fetched():
    seen = []
    android = {**ANDROID, "captions": {"playerCaptionsTracklistRenderer": {"captionTracks": [
        {"baseUrl": "https://captions.example.org/track", "languageCode": "en"}]}}}
    assert read(youtube(seen, android=android)).reason == "refused" and seen == ["ANDROID", "WEB"]


def test_a_private_address_is_refused_before_connecting():
    seen = []
    page = fetch(URL, resolver=lambda host, port: ["10.0.0.5"], transport=youtube(seen))
    assert page.reason == "refused" and seen == []


def test_an_oversized_reply_is_an_error(monkeypatch):
    small = fetch_video._Body
    monkeypatch.setattr(fetch_video, "_Body", lambda encoding: small(encoding, 100))
    assert read(youtube([])).reason == "error"


def test_the_upload_date_is_best_effort():
    def respond(request):
        if request.url.path == "/youtubei/v1/player":
            client = json.loads(request.content)["context"]["client"]["clientName"]
            return reply(json_body=ANDROID) if client == "ANDROID" else reply(500)
        return reply(text=CAPTIONS)
    page = read(httpx.MockTransport(respond))
    assert page.status == "ok" and page.published is None and page.title.startswith("Lakeview lowered")


def test_a_pasted_transcript_is_read_without_asking_for_captions(caplog):
    seen = []
    with caplog.at_level(logging.DEBUG):
        page = read(youtube(seen), transcript=PASTED)
    assert page.status == "ok" and seen == ["WEB"] and page.published == "2024-03-05"
    assert "fifty six of the sixty one companies chose to keep the four day week" in page.text
    assert "0:14" not in page.text and "1:03" not in page.text
    assert quote_time("Revenue stayed broadly the same over the trial period", page.segments) == "1:03"
    # The paste is never written to the log, at any level.
    assert all("four day week" not in record.getMessage() for record in caplog.records)
    entry = json.loads(next(r.message for r in caplog.records if '"reader": "youtube"' in r.message))
    assert entry["outcome"] == "pasted"


def test_a_paste_without_times_has_no_time():
    page = read(youtube([]), transcript=(VIDEOS / "transcript_plain.txt").read_text())
    assert page.status == "ok"
    assert quote_time("Plastic straws make up well under one percent of the plastic", page.segments) is None


def test_a_paste_too_short_to_read():
    assert read(youtube([]), transcript="0:01\nHello.").reason == "no_captions"


def test_pasted_times_in_every_form():
    segments = pasted_segments("0:00\nFirst words.\n4 minutes, 12 seconds\n4:12 Words after a time.\n"
                               "1:02:03\n\nLast words.\n")
    assert segments == [("First words.", 0), ("Words after a time.", 252), ("Last words.", 3723)]
    assert pasted_segments("Just words.\nMore words.") == [("Just words.", None), ("More words.", None)]


def test_the_older_caption_format():
    xml = '<transcript><text start="1.5" dur="2">It&amp;#39;s here</text><text start="62" dur="1">and <i>there</i></text></transcript>'
    assert caption_segments(xml) == [("It's here", 1.5), ("and there", 62.0)]


def test_a_caption_file_expands_nothing():
    xml = '<!DOCTYPE t [<!ENTITY a "aaaaaaaaaa">]><timedtext><body><p t="0">&a;&a;&a; words</p></body></timedtext>'
    assert caption_segments(xml) == [("&a;&a;&a; words", 0.0)]


@pytest.mark.parametrize("kind, channel", [("news", "news"), ("organisation", "organisation"),
                                           ("government", "organisation"), ("research", "other"),
                                           ("blog", "other"), ("reference", "other"), (None, "other")])
def test_the_channel_is_news_an_organisation_or_other(kind, channel):
    assert channel_source({"type": kind, "primary": False, "published": "2024"})["type"] == channel
    assert channel_source(None) is None


@pytest.mark.parametrize("url", ["https://vimeo.com/76979871", "https://www.tiktok.com/@a/video/1",
                                 "https://www.youtube.com/@LakeviewNews"])
def test_other_videos_still_cannot_be_read(url):
    assert fetch(url, resolver=public, transport=youtube([])).status == "unsupported"
