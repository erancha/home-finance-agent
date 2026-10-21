"""Checks which ports the compose files publish beyond the host's loopback interface.

Docker publishes on every host interface by default, which bypasses common host firewalls and
exposes a port to the whole LAN. Postgres runs with fixed demo credentials, so it is published on
127.0.0.1 only: host-mode processes still reach it at localhost. The home finance agent (8010) and
amex-agent (8020, in the end-to-end file) are the deliberate exceptions: they are the demo's entry
points, and the A2A endpoint requires the caller secret and a person's token. Any other publish
must be loopback-only.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = (ROOT / "docker-compose.yml", ROOT / "docker-compose.e2e.yml")
LOOPBACK = "127.0.0.1:"

# Key: service name. Value: the one publish allowed on every host interface.
PUBLIC_PUBLISHES = {"manager": "8010:8010", "amex-agent": "8020:8020"}


def _publishes() -> list[tuple[str, str, str]]:
    """(compose file name, service, port mapping) for every published port."""
    found: list[tuple[str, str, str]] = []
    for compose_file in COMPOSE_FILES:
        services = yaml.safe_load(compose_file.read_text(encoding="utf-8"))["services"]
        for service, spec in services.items():
            for mapping in spec.get("ports", []):
                found.append((compose_file.name, service, str(mapping)))
    return found


def test_only_the_two_agents_publish_on_every_interface():
    offenders = [
        (file, service, mapping)
        for file, service, mapping in _publishes()
        if not mapping.startswith(LOOPBACK) and PUBLIC_PUBLISHES.get(service) != mapping
    ]
    assert not offenders, f"ports published on all host interfaces: {offenders}"


def test_postgres_is_published_on_loopback_only():
    db_publishes = [m for _, service, m in _publishes() if service == "db"]
    assert db_publishes == [f"{LOOPBACK}5434:5432"], db_publishes
