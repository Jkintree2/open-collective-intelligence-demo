"""Settings read once from the environment (project decision 9)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_SITE_NAME = "Open Collective Intelligence"
DEFAULT_SITE_SENTENCE = (
    "Write what you think about an issue that matters to you. We will pull out the issue, "
    "your claim, any evidence and any solution, show you what we found, and add it to a "
    "record everyone here shares."
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
    site_sentence: str = DEFAULT_SITE_SENTENCE
    llm_api_key: str | None = None
    llm_base_url: str = DEFAULT_LLM_BASE_URL
    llm_model: str = DEFAULT_LLM_MODEL

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


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
        site_sentence=env.get("SITE_SENTENCE") or DEFAULT_SITE_SENTENCE,
        llm_api_key=env.get("LLM_API_KEY") or None,
        llm_base_url=env.get("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL,
        llm_model=env.get("LLM_MODEL") or DEFAULT_LLM_MODEL,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The one Settings object for the process, read on first use."""
    return load_settings()
