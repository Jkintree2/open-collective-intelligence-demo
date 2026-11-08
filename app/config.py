"""Settings read once from the environment (project decision 9)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

DEFAULT_SITE_NAME = "Open Collective Intelligence"
# The sentence at the top of the write page. Until 2 November 2026 it was read from SITE_SENTENCE in Render;
# since then it is the site's own, so a change to it is a change here. Render's SITE_SENTENCE (and the line
# in render.yaml) is no longer read; render.yaml is left as it is, since a change to it can make Render apply
# the whole file to John's service again.
SITE_SENTENCE = (
    "Write what you think about an issue that matters to you. Your issue, your claim, and any evidence and "
    "solution will be pulled out for you to check, then added to a database everyone here shares."
)
# v0.3: the sentence at the top of Home, with HOME_ENABLED and ASK_ENABLED (John, 4 November 2026: "or ask a
# question," goes in after "Write what you think").
HOME_SENTENCE = (
    "Write what you think, or ask a question, about an issue that matters to you. Your issue, your claim, and any "
    "evidence and solution will be pulled out for you to check, then added to a database everyone here shares."
)
DEFAULT_LLM_BASE_URL = "https://api.deepseek.com"
DEFAULT_LLM_MODEL = "deepseek-v4-flash"

REQUIRED = (
    "DEMO_PASSPHRASE",
    "SECRET_KEY",
    "ADMIN_TOKEN",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
)


@dataclass(frozen=True)
class Settings:
    demo_passphrase: str
    secret_key: str
    admin_token: str
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str = "neo4j"
    app_env: str = "production"
    site_name: str = DEFAULT_SITE_NAME
    site_sentence: str = SITE_SENTENCE
    llm_api_key: str | None = None
    llm_base_url: str = DEFAULT_LLM_BASE_URL
    llm_model: str = DEFAULT_LLM_MODEL
    accounts_enabled: bool = False
    site_url: str | None = None
    mail_from: str | None = None
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    gmail_refresh_token: str | None = None
    mail_console: bool = False
    evidence_check_enabled: bool = False
    deepseek_fetch: bool = True
    email_change_enabled: bool = False
    # Phase 3, each off unless set in the Render dashboard: Ask the record, follow-up questions on the card,
    # a place on each post (and the Near filter), the About page.
    ask_enabled: bool = False
    follow_ups_enabled: bool = False
    places_enabled: bool = False
    about_enabled: bool = False
    # v0.3, one box for Write and Ask on the Home page: "off" (the default) leaves every page as it was, "preview"
    # shows it only to the members whose emails are in HOME_PREVIEW, "on" to every signed-in member.
    home_enabled: str = "off"
    home_preview: tuple[str, ...] = ()

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


def _site_url_ok(url: str, local: bool) -> bool:
    """https always; plain http only for this machine (parsed hostname, not a prefix) when APP_ENV=local."""
    if url.startswith("https://"):
        return True
    parts = urlsplit(url)
    return local and parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1")


def _on(env: dict[str, str], name: str) -> bool:
    return (env.get(name) or "").strip().lower() in ("1", "true", "yes")


HOME_MODES = ("off", "preview", "on")


def _mode(env: dict[str, str], name: str) -> str:
    """HOME_ENABLED: off, preview or on; anything else is off."""
    value = (env.get(name) or "").strip().lower()
    return value if value in HOME_MODES else "off"


def _emails(env: dict[str, str], name: str) -> tuple[str, ...]:
    """HOME_PREVIEW: comma-separated emails, lower-cased, blanks dropped."""
    return tuple(part.strip().lower() for part in (env.get(name) or "").split(",") if part.strip())


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build Settings from `env`, or from the process environment plus `.env` when it exists.

    Exits with a one line message naming the first required variable that is unset or empty.
    """
    if env is None:
        if Path(".env").exists():
            load_dotenv(".env")
        env = dict(os.environ)
    for name in REQUIRED:
        if not env.get(name):
            raise SystemExit(f"{name} is not set")
    accounts_enabled = (env.get("ACCOUNTS_ENABLED") or "").strip().lower() in ("1", "true", "yes")
    site_url = (env.get("SITE_URL") or "").strip().rstrip("/") or None
    if accounts_enabled and not site_url:
        raise SystemExit("SITE_URL is not set")
    if accounts_enabled and not _site_url_ok(site_url, (env.get("APP_ENV") or "production") == "local"):
        raise SystemExit("SITE_URL must start with https://")
    return Settings(
        demo_passphrase=env["DEMO_PASSPHRASE"],
        secret_key=env["SECRET_KEY"],
        admin_token=env["ADMIN_TOKEN"],
        neo4j_uri=env["NEO4J_URI"],
        neo4j_username=env["NEO4J_USERNAME"],
        neo4j_password=env["NEO4J_PASSWORD"],
        neo4j_database=env.get("NEO4J_DATABASE") or "neo4j",
        app_env=env.get("APP_ENV") or "production",
        site_name=env.get("SITE_NAME") or DEFAULT_SITE_NAME,
        llm_api_key=env.get("LLM_API_KEY") or None,
        llm_base_url=env.get("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL,
        llm_model=env.get("LLM_MODEL") or DEFAULT_LLM_MODEL,
        accounts_enabled=accounts_enabled,
        site_url=site_url,
        mail_from=env.get("MAIL_FROM") or None,
        gmail_client_id=env.get("GMAIL_CLIENT_ID") or None,
        gmail_client_secret=env.get("GMAIL_CLIENT_SECRET") or None,
        gmail_refresh_token=env.get("GMAIL_REFRESH_TOKEN") or None,
        mail_console=(env.get("MAIL_CONSOLE") or "") == "1",
        evidence_check_enabled=(env.get("EVIDENCE_CHECK_ENABLED") or "").strip().lower() in ("1", "true", "yes"),
        deepseek_fetch=(env.get("DEEPSEEK_FETCH") or "1").strip() != "0",
        email_change_enabled=(env.get("EMAIL_CHANGE_ENABLED") or "").strip().lower() in ("1", "true", "yes"),
        ask_enabled=_on(env, "ASK_ENABLED"),
        follow_ups_enabled=_on(env, "FOLLOW_UPS_ENABLED"),
        places_enabled=_on(env, "PLACES_ENABLED"),
        about_enabled=_on(env, "ABOUT_ENABLED"),
        home_enabled=_mode(env, "HOME_ENABLED"),
        home_preview=_emails(env, "HOME_PREVIEW"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The one Settings object for the process, read on first use."""
    return load_settings()
