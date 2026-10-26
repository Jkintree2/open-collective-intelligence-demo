"""Phase 3: the About page (04_interface.md, "About"), behind ABOUT_ENABLED. It opens without signing in,
reads nothing from the record and calls no reading service; the three guiding documents come from the same
text that app/principles.py puts at the start of the instructions."""

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app import config, principles
from app.config import Settings
from app.pages import page

router = APIRouter()

# John's repository, as ROADMAP.md links it (CLAUDE.md rule 8: nothing personal to the builder).
REPOSITORY = "https://github.com/Jkintree2/open-collective-intelligence-demo"

# Client facing copy, word for word from docs/planning/04_interface.md.
NO_READING_SERVICE = "No reading service is set up at the moment, so cards are filled in by hand and questions cannot be asked."

PROVIDERS = {"deepseek": "DeepSeek", "openai": "OpenAI", "openrouter": "OpenRouter", "groq": "Groq",
             "mistral": "Mistral", "together": "Together AI"}


def about_on() -> None:
    if not config.get_settings().about_enabled:
        raise HTTPException(404)


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


@router.get("/about", dependencies=[Depends(about_on)])
def about(request: Request) -> Response:
    return page(request, "about.html", {
        "service": reading_service(config.get_settings()),
        "no_service": NO_READING_SERVICE,
        "repository": REPOSITORY,
        "documents": [("Statement of purpose", principles.PURPOSE),
                      ("Universal Declaration of Human Rights", principles.UDHR),
                      ("The Earth Charter", principles.EARTH_CHARTER)],
    })
