"""Phase 2: the text of a PDF behind an evidence link, and arXiv's papers; no Cypher.

app/fetch_page.py downloads the file (public addresses only, checked on every redirect) and hands it
here. The text is taken by this module run as its own process (python -m app.fetch_pdf, the file on its
standard input), which is stopped after READ_SECONDS, so a hostile file cannot hold the server; at most
MAX_PAGES pages are read, from a file of at most MAX_BYTES. The process sends each page as soon as it is
read, so a slow file stopped part way keeps the pages read before the time was up.
"""

from __future__ import annotations

import io
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, NamedTuple
from urllib.parse import urlsplit

log = logging.getLogger("oci")

MAX_BYTES = 15_000_000
MAX_PAGES = 40
# Render's free plan has a tenth of a CPU: a 15 page arXiv paper takes about 20 seconds there.
READ_SECONDS = 25
DOWNLOAD_SECONDS = 30
# Address space for the reading process. Render's free plan has 512 MB for everything, the server included;
# on Linux a 5.5 MB report peaks near 120 MB and a decompression bomb stops at about 370 MB.
MEMORY_BYTES = 384 * 1024 * 1024
ROOT = Path(__file__).resolve().parent.parent
# -E and -s: no PYTHON* variables and no user packages in the process that opens a stranger's file.
READER = [sys.executable, "-E", "-s", "-m", "app.fetch_pdf"]
PDF_TYPES = ("application/pdf", "application/x-pdf")
ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}
# New identifiers (1706.03762, with a version or not) and old ones (cs/0101001, math.GT/0309136).
ARXIV_ID = r"(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)"
ARXIV_ABS = re.compile(rf"^/abs/{ARXIV_ID}/?$")
ARXIV_PAPER = re.compile(rf"^/(?:abs|pdf)/{ARXIV_ID}(?:\.pdf)?/?$")


def is_pdf(content_type: str, url: str) -> bool:
    """A PDF by its content type, whatever the address ends in; a file sent as plain bytes counts
    only when its address ends in .pdf."""
    content_type = content_type.split(";", 1)[0].strip().lower()
    return content_type in PDF_TYPES or (content_type == "application/octet-stream"
                                         and urlsplit(url).path.lower().endswith(".pdf"))


def arxiv_paper(url: str) -> str | None:
    """The full paper's address behind an arXiv abstract page (arxiv.org/abs/<id>), else None."""
    parts = urlsplit(url)
    match = ARXIV_ABS.match(parts.path) if (parts.hostname or "").lower() in ARXIV_HOSTS else None
    return f"https://arxiv.org/pdf/{match.group(1)}" if match else None


def is_arxiv_paper(url: str) -> bool:
    parts = urlsplit(url)
    return (parts.hostname or "").lower() in ARXIV_HOSTS and bool(ARXIV_PAPER.match(parts.path))


def _date(value) -> str | None:
    try:
        return value.date().isoformat() if value else None
    except (AttributeError, ValueError):
        return None


def cap_memory(limit: int = MEMORY_BYTES) -> bool:
    """Limits this process's address space (RLIMIT_AS), where the system enforces it (Linux, as on
    Render); True when the limit was set. Elsewhere nothing is done."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        import resource

        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        resource.setrlimit(resource.RLIMIT_AS, (limit if hard == resource.RLIM_INFINITY else min(limit, hard), hard))
        return True
    except (ImportError, ValueError, OSError):
        return False


def _send(out: IO[str], item: dict) -> None:
    out.write(json.dumps(item) + "\n")
    out.flush()


def _read(data: bytes, out: IO[str]) -> None:
    """Writes one JSON line with the title and YYYY-MM-DD date, then one line per page (at most
    MAX_PAGES), each as soon as it is read."""
    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        reader.decrypt("")  # many published PDFs are locked against editing only, with an empty password
    title = created = modified = None
    try:
        meta = reader.metadata
        if meta is not None:
            title = (meta.title or "").strip() or None
            created, modified = _date(meta.creation_date), _date(meta.modification_date)
    except Exception:  # a broken information block says nothing about the text
        pass
    _send(out, {"title": title, "published": created or modified})
    for one in reader.pages[:MAX_PAGES]:
        _send(out, {"page": one.extract_text() or ""})


class Reading(NamedTuple):
    text: str
    title: str | None
    published: str | None
    pages: int
    partial: bool  # stopped (out of time, or failed) after some pages were read


def pdf_text(data: bytes, *, seconds: float | None = None, command: list[str] | None = None) -> Reading | None:
    """The PDF's text, title and date; None when not one page could be read within `seconds`. The reading
    process is killed when the time is up, and the pages it sent before then are kept."""
    started = time.perf_counter()
    outcome, out = "bad", b""
    try:
        process = subprocess.Popen(command or READER, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, cwd=ROOT)
        try:
            out, _ = process.communicate(bytes(data), timeout=seconds or READ_SECONDS)
            outcome = "ok" if process.returncode == 0 else "bad"
        except subprocess.TimeoutExpired:
            process.kill()
            out, _ = process.communicate()  # what was sent before the time was up
            outcome = "timeout"
    except OSError:
        pass
    title = published = None
    pages: list[str] = []
    for line in out.decode("utf-8", "replace").splitlines():
        try:
            item = json.loads(line)
        except ValueError:  # a line cut off when the process was stopped
            continue
        if isinstance(item, dict) and isinstance(item.get("page"), str):
            pages.append(item["page"])
        elif isinstance(item, dict) and not pages:
            title = item.get("title") if isinstance(item.get("title"), str) else None
            published = item.get("published") if isinstance(item.get("published"), str) else None
    partial = outcome != "ok" and bool(pages)
    log.info(json.dumps({"event": "pdf_read", "outcome": outcome, "pages": len(pages), "partial": partial,
                         "bytes": len(data), "ms": round((time.perf_counter() - started) * 1000)}))
    if outcome != "ok" and not pages:
        return None
    return Reading("\n".join(pages), title, published, len(pages), partial)


def page(data: bytes, url: str, about: str, stopped: str | None):
    """The Page for a downloaded PDF. `stopped` says why the download ended early (too_big or timeout):
    a PDF cut short cannot be opened."""
    from app.fetch_page import Page, cut, iso_date, tidy

    if stopped:
        return Page("unread", url, reason=stopped)
    found = pdf_text(data)
    if found is None:
        return Page("unread", url, reason="pdf")
    text = tidy(found.text)
    if len(text) < 40:
        # Pages that are pictures (a scanned document) have nothing to read (04_interface.md, PDFs); a reading
        # stopped before any text came is only a PDF that could not be opened in time.
        return Page("unread", url, reason="pdf" if found.partial else "no_text", title=found.title)
    return Page("ok", url, cut(text, about), found.title, None, iso_date(found.published))


if __name__ == "__main__":
    cap_memory()
    _read(sys.stdin.buffer.read(), sys.stdout)
