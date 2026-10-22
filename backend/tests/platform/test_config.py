from pathlib import Path

import pytest
from pydantic import ValidationError

from hfm.platform.config import Settings

REQUIRED = {
    "DATABASE_URL": "postgresql+psycopg://u:p@h:5434/d",
    "GOOGLE_CLIENT_ID": "123-abc.apps.googleusercontent.com",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key in (
        "LLM_API_KEY",
        "CARD_AGENTS_FILE",
        "HFM_FRONTEND_DIST",
        "LLM_MODEL",
        "HFM_E2E",
        "AUTH_ISSUER",
        "AUTH_JWKS_URL",
        "AUTH_PUBLIC_KEY_FILE",
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
    assert settings.card_agents_file == Path("backend/card-agents.yaml")
    assert settings.hfm_frontend_dist is None


def test_the_registry_path_is_configurable(env: pytest.MonkeyPatch) -> None:
    env.setenv("HFM_E2E", "true")
    env.setenv("CARD_AGENTS_FILE", "/card-agents.yaml")
    assert Settings().card_agents_file == Path("/card-agents.yaml")


def test_model_without_key_fails_naming_the_variable(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "anthropic:claude-haiku-5-5")
    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        Settings()


def test_blank_key_counts_as_missing(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "openai:gpt-5-mini")
    env.setenv("LLM_API_KEY", "")
    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        Settings()


def test_model_with_key_satisfies_validation(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "anthropic:claude-haiku-5-5")
    env.setenv("LLM_API_KEY", "sk-test")
    assert Settings().report_model() == ("anthropic:claude-haiku-5-5", "sk-test")


def test_unknown_provider_fails_naming_it(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "gemini:x")
    with pytest.raises(ValidationError, match="gemini"):
        Settings()


def test_model_without_provider_prefix_fails(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "claude-haiku-5-5")
    with pytest.raises(ValidationError, match="provider:model"):
        Settings()


def test_missing_google_client_id_fails(env: pytest.MonkeyPatch) -> None:
    env.setenv("HFM_E2E", "true")
    env.delenv("GOOGLE_CLIENT_ID")
    with pytest.raises(ValidationError, match="google_client_id"):
        Settings()


def test_token_verification_defaults_to_google(env: pytest.MonkeyPatch) -> None:
    env.setenv("HFM_E2E", "true")
    settings = Settings()
    assert settings.auth_issuer == "https://accounts.google.com"
    assert settings.auth_jwks_url == "https://www.googleapis.com/oauth2/v3/certs"
    assert settings.auth_public_key_file is None
    env.setenv("AUTH_ISSUER", "hfm-e2e")
    env.setenv("AUTH_PUBLIC_KEY_FILE", "/e2e/public.pem")
    settings = Settings()
    assert settings.auth_issuer == "hfm-e2e"
    assert settings.auth_public_key_file == Path("/e2e/public.pem")


def test_redis_url_is_optional_and_kept_secret(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL", "openai:gpt-5-nano")
    env.setenv("LLM_API_KEY", "k")
    env.setenv("REDIS_URL", "")
    assert Settings().redis_url is None
    env.setenv("REDIS_URL", "redis://:hunter2@redis:6379/0")
    url = Settings().redis_url
    assert url is not None
    assert url.get_secret_value() == "redis://:hunter2@redis:6379/0"
    assert "hunter2" not in repr(url)
