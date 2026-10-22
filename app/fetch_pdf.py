"""Phase 2: the text of a PDF behind an evidence link, and arXiv's papers; no Cypher.

app/fetch_page.py downloads the file (public addresses only, checked on every redirect) and hands it
here. The text is taken by this module run as its own process (python -m app.fetch_pdf, the file on its
standard input), which is stopped after READ_SECONDS, so a hostile file cannot hold the server; at most
MAX_PAGES pages are read, from a file of at most MAX_BYTES.
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
from urllib.parse import urlsplit

log = logging.getLogger("oci")

MAX_BYTES = 15_000_000
MAX_PAGES = 40
READ_SECONDS = 10
DOWNLOAD_SECONDS = 30
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


def _read(data: bytes) -> tuple[str, str | None, str | None]:
    """(text of the first MAX_PAGES pages, title, YYYY-MM-DD) from the file's bytes."""
    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        reader.decrypt("")  # many published PDFs are locked against editing only, with an empty password
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PAGES])
    title = created = modified = None
    try:
        meta = reader.metadata
        if meta is not None:
            title = (meta.title or "").strip() or None
            created, modified = _date(meta.creation_date), _date(meta.modification_date)
    except Exception:  # a broken information block says nothing about the text
        pass
    return text, title, created or modified


def pdf_text(data: bytes, *, seconds: float = READ_SECONDS,
             command: list[str] | None = None) -> tuple[str, str | None, str | None] | None:
    """(text, title, published), or None when the file cannot be read within `seconds`; the reading
    process is killed when the time is up."""
    started = time.perf_counter()
    outcome, found = "bad", None
    try:
        done = subprocess.run(command or READER, input=bytes(data), capture_output=True, timeout=seconds,
                              cwd=ROOT, check=False)
        if done.returncode == 0:
            reply = json.loads(done.stdout)
            outcome, found = "ok", (reply["text"], reply["title"], reply["published"])
    except subprocess.TimeoutExpired:
        outcome = "timeout"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    log.info(json.dumps({"event": "pdf_read", "outcome": outcome, "bytes": len(data),
                         "ms": round((time.perf_counter() - started) * 1000)}))
    return found


def page(data: bytes, url: str, about: str, stopped: str | None):
    """The Page for a downloaded PDF. `stopped` says why the download ended early (too_big or timeout):
    a PDF cut short cannot be opened."""
    from app.fetch_page import Page, cut, iso_date, tidy

    if stopped:
        return Page("unread", url, reason=stopped)
    found = pdf_text(data)
    if found is None:
        return Page("unread", url, reason="pdf")
    text, title, published = found
    text = tidy(text)
    if len(text) < 40:
        # Pages that are pictures (a scanned document): nothing to read (04_interface.md, PDFs).
        return Page("unread", url, reason="no_text", title=title)
    return Page("ok", url, cut(text, about), title, None, iso_date(published))


if __name__ == "__main__":
    text, title, published = _read(sys.stdin.buffer.read())
    sys.stdout.write(json.dumps({"text": text, "title": title, "published": published}))
