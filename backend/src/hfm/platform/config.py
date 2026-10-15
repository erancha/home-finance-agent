"""Process settings read from the environment and backend/.env, validated at startup."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hfm.adapters.report_writer import SUPPORTED_PROVIDERS


class Settings(BaseSettings):
    """A blank variable counts as unset, so a blank OPTIONAL key keeps its default."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", frozen=True, env_ignore_empty=True
    )

    database_url: SecretStr
    llm_model: str | None = None
    """"provider:model" for a supported provider; required unless hfm_e2e is set."""
    hfm_e2e: bool = False
    """Set by docker-compose.e2e.yml alone: the report is a canned text, and no model or API key is
    read, so the end-to-end test is deterministic and free."""
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    amex_agent_url: str = "http://localhost:8020"
    amex_agent_token: SecretStr
    amex_agent_browser_url: str | None = None
    """Where a person's browser reaches amex-agent; unset means amex_agent_url, which is that
    address whenever the home finance agent runs on the host rather than in Docker."""
    agents_config: Path = Path("config/agents.yaml")
    budget_config: Path = Path("config/budget.yaml")
    hfm_frontend_dist: Path | None = None

    @model_validator(mode="after")
    def _require_provider_key(self) -> Self:
        if self.hfm_e2e:
            return self
        if self.llm_model is None:
            raise ValueError("LLM_MODEL must be set to provider:model")
        provider, separator, model = self.llm_model.partition(":")
        if not separator or not model:
            raise ValueError(f"LLM_MODEL={self.llm_model!r} must be provider:model")
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"LLM_MODEL provider {provider!r} is not one of {', '.join(SUPPORTED_PROVIDERS)}"
            )
        if self._provider_key(provider) is None:
            raise ValueError(
                f"LLM_MODEL={self.llm_model} needs {_key_field(provider).upper()} to be set"
            )
        return self

    def amex_browser_url(self) -> str:
        if self.amex_agent_browser_url is None:
            return self.amex_agent_url
        return self.amex_agent_browser_url

    def report_model(self) -> tuple[str, str]:
        """The validated provider:model and its API key; only outside the end-to-end test."""
        assert not self.hfm_e2e and self.llm_model is not None, "validated at construction"
        key = self._provider_key(self.llm_model.partition(":")[0])
        assert key is not None, "validated at construction"
        return self.llm_model, key.get_secret_value()

    def _provider_key(self, provider: str) -> SecretStr | None:
        key: SecretStr | None = getattr(self, _key_field(provider))
        return key


def _key_field(provider: str) -> str:
    return f"{provider}_api_key"


@lru_cache
def get_settings() -> Settings:
    # Required fields come from the environment, which mypy cannot see.
    return Settings()  # type: ignore[call-arg]
