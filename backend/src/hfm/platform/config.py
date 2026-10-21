"""Process settings read from the environment and backend/.env, validated at startup."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hfm.adapters.config_files import REGISTRY_FILE_NAME
from hfm.adapters.google_tokens import GOOGLE_ISSUER, GOOGLE_JWKS_URL
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
    llm_api_key: SecretStr | None = None
    """The key of the provider llm_model names; required with it."""
    google_client_id: str
    """The OAuth client of this agent's Sign in with Google button; the audience every token
    must name."""
    auth_issuer: str = GOOGLE_ISSUER
    auth_jwks_url: str = GOOGLE_JWKS_URL
    auth_public_key_file: Path | None = None
    """Test only: a PEM public key that verifies tokens instead of the issuer's published keys,
    so the end-to-end test signs its own tokens and never reaches Google."""
    card_agents_file: Path = Path("backend") / REGISTRY_FILE_NAME
    """The card-agent registry scripts/add-card-agent.sh writes; absent means no card agents.
    Relative to the working directory, the repo root on the host; compose sets this key to the
    path it mounts the file at."""
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
        if self.llm_api_key is None:
            raise ValueError(f"LLM_MODEL={self.llm_model} needs LLM_API_KEY to be set")
        return self

    def report_model(self) -> tuple[str, str]:
        """The validated provider:model and its API key; only outside the end-to-end test."""
        assert not self.hfm_e2e and self.llm_model is not None, "validated at construction"
        assert self.llm_api_key is not None, "validated at construction"
        return self.llm_model, self.llm_api_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    # Required fields come from the environment, which mypy cannot see.
    return Settings()  # type: ignore[call-arg]
