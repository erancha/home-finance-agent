"""Loads the card-agent registry and the monthly budget from their YAML files."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from hfm.domain.models import AgentConfig, Budget
from hfm.domain.taxonomy import require_category

REGISTRY_FILE_NAME = "card-agents.yaml"
"""The registry's file name beside backend/.env; scripts/add-card-agent.sh writes it."""

_FIELDS = ("name", "url", "browser_url", "shared_secret")


def load_card_agents(path: Path) -> dict[str, AgentConfig]:
    """Agent name to its config, in file order. No file, an empty file and an empty list all mean
    no card agents, a legal state; a bad entry is refused naming the entry and the field."""
    if not path.exists():
        return {}
    document = yaml.safe_load(path.read_text())
    if document is None:
        return {}
    entries = document["agents"] or []
    if not isinstance(entries, list):
        raise TypeError(f"{path}: agents must be a list, one entry per card agent")
    agents: dict[str, AgentConfig] = {}
    for position, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise TypeError(f"entry {position} in {path} must be a mapping of name, url, "
                             "browser_url and shared_secret")
        label = f"agent '{entry['name']}'" if entry.get("name") else f"entry {position}"
        for field in _FIELDS:
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"{label} in {path} lacks {field}")
        for field in ("url", "browser_url"):
            parts = urlsplit(entry[field])
            if parts.scheme not in ("http", "https") or not parts.netloc:
                raise ValueError(f"{label} in {path}: {field} must be an http(s) URL")
        name = entry["name"]
        if name in agents:
            raise ValueError(f"agent '{name}' is listed twice in {path}")
        agents[name] = AgentConfig(
            name=name, url=entry["url"], token=entry["shared_secret"],
            browser_url=entry["browser_url"],
        )
    return agents


def load_budget(path: Path) -> Budget:
    data = yaml.safe_load(path.read_text())
    limits = {require_category(c): Decimal(str(v)) for c, v in data["limits"].items()}
    return Budget(currency=data["currency"], limits=limits)
