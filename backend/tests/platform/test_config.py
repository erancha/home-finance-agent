from pathlib import Path

import pytest
from pydantic import ValidationError

from hfm.platform.config import Settings

REQUIRED = {"DATABASE_URL": "postgresql+psycopg://u:p@h:5434/d", "AMEX_AGENT_TOKEN": "secret"}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "AMEX_AGENT_URL",
        "AMEX_AGENT_BROWSER_URL",
        "HFM_FRONTEND_DIST",
        "LLM_MODEL",
        "HFM_E2E",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_a_model_is_required(env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="LLM_MODEL must be set"):
        Settings()


def test_fake_is_not_a_model(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "fake")
    with pytest.raises(ValidationError, match="must be provider:model"):
        Settings()


def test_the_end_to_end_test_needs_no_model_or_key(env: pytest.MonkeyPatch) -> None:
    env.setenv("HFM_E2E", "true")
    settings = Settings()
    assert settings.hfm_e2e
    assert settings.amex_agent_url == "http://localhost:8020"
    assert settings.agents_config == Path("config/agents.yaml")
    assert settings.hfm_frontend_dist is None


def test_browser_url_is_the_agent_url_unless_set(env: pytest.MonkeyPatch) -> None:
    env.setenv("HFM_E2E", "true")
    env.setenv("AMEX_AGENT_URL", "http://amex-agent:8020")
    assert Settings().amex_browser_url() == "http://amex-agent:8020"
    env.setenv("AMEX_AGENT_BROWSER_URL", "http://localhost:8020")
    assert Settings().amex_browser_url() == "http://localhost:8020"


def test_anthropic_model_without_key_fails_naming_the_variable(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "anthropic:claude-haiku-5-5")
    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
        Settings()


def test_blank_key_counts_as_missing(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "openai:gpt-5-mini")
    env.setenv("OPENAI_API_KEY", "")
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings()


def test_provider_key_satisfies_validation(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "anthropic:claude-haiku-5-5")
    env.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert Settings().report_model() == ("anthropic:claude-haiku-5-5", "sk-test")


def test_unknown_provider_fails_naming_it(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "gemini:x")
    with pytest.raises(ValidationError, match="gemini"):
        Settings()


def test_model_without_provider_prefix_fails(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "claude-haiku-5-5")
    with pytest.raises(ValidationError, match="provider:model"):
        Settings()


def test_missing_agent_token_fails(env: pytest.MonkeyPatch) -> None:
    env.setenv("HFM_E2E", "true")
    env.delenv("AMEX_AGENT_TOKEN")
    with pytest.raises(ValidationError, match="amex_agent_token"):
        Settings()
