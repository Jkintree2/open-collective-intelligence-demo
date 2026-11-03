"""docs/code-map.md names every module, script, template and page script, and every label and type a copy
can hold; the operator's guide stays plain (CLAUDE.md rule 5); and nothing the repo publishes is personal to the
builder or names a commercial term (rule 8)."""

import hashlib
import re
from pathlib import Path

from app.backup import DIRECTIONS, LABEL_KEYS

ROOT = Path(__file__).resolve().parent.parent


def section(path: str, heading: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    return text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def named(name: str, text: str) -> bool:
    return re.search(rf"(?<![\w.]){re.escape(name)}(?![\w])", text) is not None


def test_layout_names_every_module_script_template_and_page_script():
    layout = (ROOT / "docs/code-map.md").read_text(encoding="utf-8")
    files = [*ROOT.glob("app/*.py"), *ROOT.glob("scripts/*.py"), *ROOT.glob("app/static/*")]
    missing = [p.name for p in files if p.name != "__init__.py" and not named(p.name, layout)]
    templates = next(line for line in layout.splitlines() if line.startswith("app/templates/"))
    missing += [p.name for p in ROOT.glob("app/templates/*.html") if not named(p.stem, templates)]
    assert missing == []


def test_schema_in_brief_names_every_label_and_relationship_type():
    brief = section("CLAUDE.md", "Schema in brief")
    assert [name for name in [*LABEL_KEYS, *DIRECTIONS] if f"`{name}" not in brief] == []


# "language model" is John's own word for the reading service since 28 October (CLAUDE.md rule 5).
TECHNICAL = re.compile(r"\b(node|edge|graph|cypher|(?<!language )model|extraction|entity)s?\b", re.I)


def test_the_operators_guide_is_plain_and_covers_phase_1():
    guide = (ROOT / "docs/operators-guide.md").read_text(encoding="utf-8")
    assert "\u2013" not in guide and "\u2014" not in guide and " - " not in guide
    assert TECHNICAL.search(guide) is None, TECHNICAL.search(guide)
    assert "passphrase is the only lock" not in guide
    for phrase in ("Enter a person", "This person has agreed to be entered", "Send the invitation again",
                   "Send a password link", "Withdraw", "Switch off", "Switch on", "first account",
                   "Forgot your password?", "My account", "My statements", "Sending email", "Tidy this issue",
                   "Changes to the issues", "Sending email from your Gmail"):
        assert phrase in guide, phrase


def test_the_operators_guide_covers_phase_3():
    guide = section("docs/operators-guide.md", "Talking to the database")
    for phrase in ("`ASK_ENABLED`", "`FOLLOW_UPS_ENABLED`", "`PLACES_ENABLED`", "`ABOUT_ENABLED`", "Add to my statement",
                   "part of the public statement", "Near", "start again when the site restarts", "half a US cent",
                   "a third of a US cent", "After switching it on", "app/guiding/udhr.txt"):
        assert phrase in guide, phrase
    assert guide.count("**After switching it on:**") == 4


# Rule 8. The personal words are kept as sha256 digests of their lower-case spelling, so this file does not hold
# them either. A word matches whole: "Estonia" is another word.
PUBLISHED = ("app", "scripts", "docs", "README.md", "ROADMAP.md", "CLAUDE.md", ".env.example")
PERSONAL = {
    "b60a134e7eeb169bdc7fa5811f9dfc8ae8c6a874f4c6e9839f5c1dbc8349abbb",  # a first name
    "50a4c30432aade0bfa30f2ebd68976e87075bd5cfb68af44a63db243f7c299b5",  # a surname
    "d20e7f51ebc2cf24107b12bc077fe68d49a01cbc71f9d0471ae1479e0e188c7c",  # a firm's name, two words
    "a7b0d4efcd9fd1bc79f1711347c8314a2d5124f4a5ef829875ae421b0abe2dd3",  # an email address's name
    "bd7d23838a0f59b9101b40f05c7fe8604624f45c1d878ce1f4de3be04525a419",  # an account name, less its digits
}
COMMERCIAL = re.compile(r"(?i:no charge|invoice)|\bSOW\b")


def published_lines():
    for name in PUBLISHED:
        path = ROOT / name
        for file in sorted(path.rglob("*")) if path.is_dir() else [path]:
            if file.is_file() and "__pycache__" not in file.parts:
                text = file.read_text(encoding="utf-8", errors="ignore")
                for number, line in enumerate(text.splitlines(), 1):
                    yield f"{file.relative_to(ROOT)}:{number}", line


def personal(line: str) -> bool:
    words = re.findall(r"[a-z]+", line.lower())
    phrases = {*words, *(f"{a} {b}" for a, b in zip(words, words[1:]))}
    return any(hashlib.sha256(phrase.encode()).hexdigest() in PERSONAL for phrase in phrases)


def test_nothing_published_is_personal_to_the_builder_or_commercial():
    hits = [where for where, line in published_lines() if personal(line) or COMMERCIAL.search(line)]
    assert hits == [], "\n".join(hits)
