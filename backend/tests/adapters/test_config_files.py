from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from hfm.adapters.config_files import load_budget, load_card_agents
from hfm.domain.models import AgentConfig


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cfg.yaml"
    path.write_text(text)
    return path


REGISTRY = """
agents:
  - name: amex
    url: http://host.docker.internal:8020/
    browser_url: http://localhost:8020
    shared_secret: s3cret-1
"""


def test_load_card_agents_reads_entries_in_order(tmp_path: Path) -> None:
    second = REGISTRY.replace("amex", "visa").removeprefix("\nagents:\n")
    assert list(load_card_agents(write(tmp_path, REGISTRY + second))) == ["amex", "visa"]
    assert load_card_agents(write(tmp_path, REGISTRY))["amex"] == AgentConfig(
        "amex", "http://host.docker.internal:8020/", "s3cret-1", "http://localhost:8020"
    )


@pytest.mark.parametrize("text", ["agents: []\n", "", "# emptied by the operator\n"])
def test_no_registry_or_no_entries_means_no_agents(tmp_path: Path, text: str) -> None:
    assert load_card_agents(tmp_path / "none.yaml") == {}
    assert load_card_agents(write(tmp_path, text)) == {}


@pytest.mark.parametrize("field", ["name", "url", "browser_url", "shared_secret"])
def test_a_blank_or_missing_field_is_refused_naming_it(tmp_path: Path, field: str) -> None:
    value = {
        "name": "amex", "url": "http://host.docker.internal:8020/",
        "browser_url": "http://localhost:8020", "shared_secret": "s3cret-1",
    }[field]
    blank = REGISTRY.replace(f"{field}: {value}", f"{field}: ''")
    with pytest.raises(ValueError, match=field):
        load_card_agents(write(tmp_path, blank))
    missing = "\n".join(line for line in REGISTRY.splitlines() if f"{field}:" not in line)
    if field == "name":
        missing = missing.replace("    url:", "  - url:", 1)
    with pytest.raises(ValueError, match=field):
        load_card_agents(write(tmp_path, missing + "\n"))


@pytest.mark.parametrize("text", ["agents:\n  - amex\n", "agents:\n  url: http://x\n"])
def test_a_registry_whose_entries_are_not_mappings_is_refused(tmp_path: Path, text: str) -> None:
    with pytest.raises(TypeError, match="entry|list"):
        load_card_agents(write(tmp_path, text))


@pytest.mark.parametrize("url", ["localhost:8020", "ftp://x", "http://"])
def test_a_url_without_an_http_origin_is_refused(tmp_path: Path, url: str) -> None:
    with pytest.raises(ValueError, match="amex.*url"):
        load_card_agents(
            write(tmp_path, REGISTRY.replace("http://host.docker.internal:8020/", url))
        )


def test_a_name_listed_twice_is_refused(tmp_path: Path) -> None:
    path = write(tmp_path, REGISTRY + REGISTRY.removeprefix("\nagents:\n"))
    with pytest.raises(ValueError, match="'amex' is listed twice"):
        load_card_agents(path)


def test_load_budget_converts_amounts_to_decimal(tmp_path: Path) -> None:
    budget = load_budget(
        write(tmp_path, "currency: ILS\nlimits:\n  transport: 600\n  dining: 80.5\n")
    )
    assert budget.currency == "ILS"
    assert budget.limits == {"transport": Decimal(600), "dining": Decimal("80.5")}


def test_load_budget_rejects_unknown_category(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="pharmacy"):
        load_budget(write(tmp_path, "currency: ILS\nlimits:\n  pharmacy: 1\n"))


def test_a_missing_budget_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_budget(tmp_path / "none.yaml")


def test_the_budget_example_loads() -> None:
    config = Path(__file__).parents[3] / "config"
    assert "groceries" in load_budget(config / "budget.example.yaml").limits
