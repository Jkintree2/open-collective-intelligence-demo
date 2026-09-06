import pytest

from app.config import DEFAULT_SITE_NAME, DEFAULT_SITE_SENTENCE, load_settings

FULL = {
    "DEMO_PASSPHRASE": "three plain words",
    "SECRET_KEY": "secret",
    "ADMIN_TOKEN": "admin",
    "NEO4J_URI": "neo4j://localhost:7687",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "localpass",
}


def test_missing_variable_stops_startup_naming_it():
    env = dict(FULL)
    del env["DEMO_PASSPHRASE"]
    with pytest.raises(SystemExit) as raised:
        load_settings(env)
    assert str(raised.value) == "DEMO_PASSPHRASE is not set"


def test_empty_variable_counts_as_missing():
    env = dict(FULL, SECRET_KEY="")
    with pytest.raises(SystemExit, match="SECRET_KEY is not set"):
        load_settings(env)


def test_defaults_apply_when_optional_variables_are_absent():
    settings = load_settings(FULL)
    assert settings.site_name == DEFAULT_SITE_NAME
    assert settings.site_sentence == DEFAULT_SITE_SENTENCE
    assert settings.neo4j_database == "neo4j"
    assert settings.app_env == "production"
    assert settings.llm_base_url == "https://api.deepseek.com"
    assert settings.llm_model == "deepseek-v4-flash"
    assert settings.llm_api_key is None
