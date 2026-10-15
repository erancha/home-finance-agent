"""Loads the card-agent list and the monthly budget from the YAML files under config/."""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import yaml

from hfm.domain.models import AgentConfig, Budget
from hfm.domain.taxonomy import require_category


def load_agents(path: Path, env: Mapping[str, str]) -> dict[str, AgentConfig]:
    """Agent name to its config, in file order; a name listed twice is refused."""
    agents: dict[str, AgentConfig] = {}
    for e in yaml.safe_load(path.read_text())["agents"]:
        name = e["name"]
        if name in agents:
            raise ValueError(f"agent '{name}' is listed twice in {path}")
        agents[name] = AgentConfig(
            name=name,
            url=_require_env(env, e["url_env"], name),
            token=_require_env(env, e["token_env"], name),
            browser_url=_require_env(env, e["browser_url_env"], name),
        )
    return agents


def _require_env(env: Mapping[str, str], variable: str, agent: str) -> str:
    if variable not in env:
        raise KeyError(f"environment variable {variable} for agent '{agent}' is not set")
    return env[variable]


def load_budget(path: Path) -> Budget:
    data = yaml.safe_load(path.read_text())
    limits = {require_category(c): Decimal(str(v)) for c, v in data["limits"].items()}
    return Budget(currency=data["currency"], limits=limits)
