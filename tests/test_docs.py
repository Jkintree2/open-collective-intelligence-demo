"""CLAUDE.md names every module, script, template and page script, and every label and type a copy
can hold; the operator's guide stays plain (CLAUDE.md rules 5 and 8)."""

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
    layout = section("CLAUDE.md", "Layout")
    files = [*ROOT.glob("app/*.py"), *ROOT.glob("scripts/*.py"), *ROOT.glob("app/static/*")]
    missing = [p.name for p in files if p.name != "__init__.py" and not named(p.name, layout)]
    templates = next(line for line in layout.splitlines() if line.startswith("app/templates/"))
    missing += [p.name for p in ROOT.glob("app/templates/*.html") if not named(p.stem, templates)]
    assert missing == []


def test_schema_in_brief_names_every_label_and_relationship_type():
    brief = section("CLAUDE.md", "Schema in brief")
    assert [name for name in [*LABEL_KEYS, *DIRECTIONS] if f"`{name}" not in brief] == []
