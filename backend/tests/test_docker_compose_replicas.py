"""Checks the replica layout of the compose files.

The development stack runs more than one replica of the home finance agent behind the edge,
sharing live events through Redis, so the demo shows a review served by whichever replica takes
each request.
The end-to-end test answers a question the instant it arrives, which can reach the replica that
does not own the run before its status settles, so it runs one replica.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _service(compose_file: str, name: str) -> dict:
    return yaml.safe_load((ROOT / compose_file).read_text(encoding="utf-8"))["services"][name]


def test_the_development_stack_runs_several_agent_replicas_sharing_redis():
    manager = _service("docker-compose.yml", "manager")
    assert manager["deploy"]["replicas"] > 1
    assert manager["environment"]["REDIS_URL"].startswith("redis://redis:")
    assert manager["depends_on"]["redis"] == {"condition": "service_healthy"}


def test_the_end_to_end_stack_runs_one_agent_replica():
    assert _service("docker-compose.e2e.yml", "manager")["deploy"]["replicas"] == 1
