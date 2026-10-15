from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from hfm.adapters.config_files import load_agents, load_budget
from hfm.domain.models import AgentConfig


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cfg.yaml"
    path.write_text(text)
    return path


AGENTS = """
agents:
  - name: amex
    url_env: AMEX_AGENT_URL
    token_env: AMEX_AGENT_TOKEN
    browser_url_env: AMEX_AGENT_BROWSER_URL
"""
ENV = {
    "AMEX_AGENT_URL": "http://amex",
    "AMEX_AGENT_TOKEN": "t",
    "AMEX_AGENT_BROWSER_URL": "http://localhost:8020",
}


def test_load_agents_resolves_env_and_fails_on_missing(tmp_path: Path) -> None:
    path = write(tmp_path, AGENTS)
    assert load_agents(path, ENV) == {
        "amex": AgentConfig("amex", "http://amex", "t", "http://localhost:8020")
    }
    for variable in ENV:
        with pytest.raises(KeyError, match=f"{variable}.*amex"):
            load_agents(path, {k: v for k, v in ENV.items() if k != variable})


def test_load_agents_refuses_a_name_listed_twice(tmp_path: Path) -> None:
    path = write(tmp_path, AGENTS + AGENTS.removeprefix("\nagents:\n"))
    with pytest.raises(ValueError, match="'amex' is listed twice"):
        load_agents(path, ENV)


def test_load_budget_converts_amounts_to_decimal(tmp_path: Path) -> None:
    budget = load_budget(
        write(tmp_path, "currency: ILS\nlimits:\n  transport: 600\n  dining: 80.5\n")
    )
    assert budget.currency == "ILS"
    assert budget.limits == {"transport": Decimal(600), "dining": Decimal("80.5")}


def test_load_budget_rejects_unknown_category(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="pharmacy"):
        load_budget(write(tmp_path, "currency: ILS\nlimits:\n  pharmacy: 1\n"))


def test_missing_files_raise_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_agents(tmp_path / "none.yaml", {})
    with pytest.raises(FileNotFoundError):
        load_budget(tmp_path / "none.yaml")


def test_shipped_config_files_load() -> None:
    config = Path(__file__).parents[3] / "config"
    assert list(load_agents(config / "agents.yaml", ENV)) == ["amex"]
    assert "groceries" in load_budget(config / "budget.yaml").limits
