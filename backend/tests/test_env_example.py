"""Checks that backend/.env.example documents exactly the keys something reads.

A key counts as documented when a line of the file assigns it, commented out or not
(KEY=value or # KEY=value). The rule:
- every Settings field, upper-cased (Settings has no env prefix), is documented;
- every url_env and token_env named in config/agents.yaml is documented;
- every documented key is one of those, or one of the operational keys below, which the scripts,
  compose, LangGraph or the logging setup read instead of Settings.
"""
import re
from pathlib import Path

import yaml

from hfm.platform.config import Settings
from hfm.platform.logging import ENV_PREFIX

ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = ROOT / "backend" / ".env.example"
AGENTS_YAML = ROOT / "config" / "agents.yaml"

_ASSIGNMENT = re.compile(r"^(?:#\s*)?([A-Z][A-Z0-9_]*)=", re.MULTILINE)

OPERATIONAL_KEYS = {
    # scripts/common.sh and docker-compose.yml: where the Java repo and its statements live
    "AMEX_AGENT_DIR",
    "AMEX_STATEMENTS_DIR",
    # read by LangGraph itself at import time
    "LANGGRAPH_STRICT_MSGPACK",
    # hfm.platform.logging.configure_logging
    f"{ENV_PREFIX}LOG_LEVEL",
    f"{ENV_PREFIX}LOG_LEVELS",
}


def _documented_keys() -> set[str]:
    return set(_ASSIGNMENT.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


def _settings_keys() -> set[str]:
    return {name.upper() for name in Settings.model_fields}


def _agent_keys() -> set[str]:
    agents = yaml.safe_load(AGENTS_YAML.read_text(encoding="utf-8"))["agents"]
    return {agent[field] for agent in agents for field in ("url_env", "token_env")}


def test_every_settings_field_is_documented():
    missing = sorted(_settings_keys() - _documented_keys())
    assert not missing, f"Settings fields missing from backend/.env.example: {missing}"


def test_every_agent_variable_is_documented():
    missing = sorted(_agent_keys() - _documented_keys())
    assert not missing, f"config/agents.yaml variables missing from backend/.env.example: {missing}"


def test_no_documented_key_is_unknown():
    known = _settings_keys() | _agent_keys() | OPERATIONAL_KEYS
    unknown = sorted(_documented_keys() - known)
    assert not unknown, f"backend/.env.example documents keys nothing reads: {unknown}"
