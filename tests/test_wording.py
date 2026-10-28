"""John, 28 October: "shared database" instead of "shared record". No page or page script says "the record"
where a tester can read it (Jinja and script comments aside). Code names such as card.js keep their words."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
RECORD = re.compile(r"\b(?:the|a|shared) record\b", re.IGNORECASE)


def test_no_page_says_the_record():
    for path in sorted((APP / "templates").glob("*.html")):
        text = re.sub(r"{#.*?#}", "", path.read_text(encoding="utf-8"), flags=re.S)
        assert RECORD.search(text) is None, (path.name, RECORD.search(text))


def test_no_page_script_string_says_the_record():
    for path in sorted((APP / "static").glob("*.js")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("//", 1)[0]
            strings = re.findall(r"'[^']*'|`[^`]*`", code)
            assert not any(RECORD.search(s) for s in strings), (path.name, number, line.strip())


# John, 28 October (email after the call): "language model" instead of "reading service" throughout.
SERVICE = re.compile(r"reading service", re.IGNORECASE)


def test_no_page_or_page_script_string_says_reading_service():
    for path in sorted((APP / "templates").glob("*.html")):
        text = re.sub(r"{#.*?#}", "", path.read_text(encoding="utf-8"), flags=re.S)
        assert SERVICE.search(text) is None, path.name
    for path in sorted((APP / "static").glob("*.js")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            strings = re.findall(r"'[^']*'|`[^`]*`", line.split("//", 1)[0])
            assert not any(SERVICE.search(s) for s in strings), (path.name, number, line.strip())


def test_the_messages_the_server_sends_say_language_model():
    from app import admin, main, routes_ask
    for message in [main.NOT_ANSWERING, routes_ask.NO_SERVICE, *admin.ERRORS.values()]:
        assert "language model" in message and SERVICE.search(message) is None, message
