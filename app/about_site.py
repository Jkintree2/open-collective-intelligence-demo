"""The About page's own text (app/templates/_about_site.html), drawn on the page and given to Ask as plain words, D4
(John, 9 November 2026). John edits the site's description in that template. A plain module, so Ask reads it without
the web app."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import Settings
from app.fetch_page import html_text

# John's repository, as ROADMAP.md links it (CLAUDE.md rule 8: nothing personal to the builder).
REPOSITORY = "https://github.com/Jkintree2/open-collective-intelligence-demo"

# Client facing copy, word for word from docs/planning/04_interface.md.
NO_READING_SERVICE = "No language model is set up at the moment, so forms are filled in by hand and questions cannot be asked."
# The same line without Ask the record (ASK_ENABLED unset), which then has no questions to speak of.
NO_READING_SERVICE_CARDS = "No language model is set up at the moment, so forms are filled in by hand."

PROVIDERS = {"deepseek": "DeepSeek", "openai": "OpenAI", "openrouter": "OpenRouter", "groq": "Groq",
             "mistral": "Mistral", "together": "Together AI"}


def provider(base_url: str) -> str:
    """The company behind LLM_BASE_URL, by a known name in its host, else the host itself."""
    host = (urlparse(base_url).hostname or base_url).lower()
    for part, name in PROVIDERS.items():
        if part in host:
            return name
    return host.removeprefix("api.")


def reading_service(settings: Settings) -> dict[str, str] | None:
    if not settings.llm_api_key:
        return None
    return {"provider": provider(settings.llm_base_url), "version": settings.llm_model}


def site_context(settings: Settings) -> dict[str, Any]:
    """What _about_site.html draws from, on the page and for Ask."""
    return {"service": reading_service(settings), "no_service": NO_READING_SERVICE,
            "no_service_cards": NO_READING_SERVICE_CARDS, "evidence_check": settings.evidence_check_enabled,
            "repository": REPOSITORY}


_TEMPLATES = Environment(loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
                         autoescape=select_autoescape())


def site_text(settings: Settings) -> str:
    """The About page's text above the three documents, as plain words for Ask's instructions (John, 9 November):
    the partial the page draws, with the name and switches of `settings`."""
    html = _TEMPLATES.get_template("_about_site.html").render(**site_context(settings), on=settings.switches,
                                                              site_name=settings.site_name)
    return html_text(html)[0]
