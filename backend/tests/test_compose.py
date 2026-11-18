"""Checks how the compose files wire the agent, its database and the edge, here and on EC2.

Docker publishes on every host interface by default, which bypasses common host firewalls and
exposes a port to the whole LAN. Postgres is published on the loopback interface only, so a psql
or an agent started on the host still reaches it at localhost. The nginx edge in front of the
manager and amex-agent (in the end-to-end file) are the deliberate exceptions: they are the demo's
entry points, and the A2A endpoint requires the caller secret and a person's token. The manager
publishes nothing: the browser reaches it through the edge alone, so a second replica needs no
port of its own.

Compose runs against the EC2 instance's Docker daemon from this machine, where a bind mount would
name a path the instance lacks, so the stack mounts no file of this machine. Each container
receives only the keys it reads, and learns the in-network database address from compose rather
than from the host form of the settings files.
"""

from pathlib import Path
from typing import Any

import yaml

from hfm.platform.config import Settings
from hfm.platform.logging import ENV_PREFIX

ROOT = Path(__file__).resolve().parents[2]
LOOPBACK = "127.0.0.1:"
DB_PUBLISH = "${DB_HOST_PORT:?set in stack-params.sh}:${DB_PORT:?set in stack-params.sh}"


class _ComposeLoader(yaml.SafeLoader):
    """Reads an override file's !override tag as the plain value it replaces the base value with."""


_ComposeLoader.add_constructor(
    "!override", lambda loader, node: loader.construct_sequence(node)  # type: ignore[arg-type]
)


def _compose(name: str) -> dict[str, Any]:
    return yaml.load((ROOT / name).read_text(encoding="utf-8"), Loader=_ComposeLoader)


COMPOSE = _compose("docker-compose.yml")
SERVICES = COMPOSE["services"]
EC2_SERVICES = _compose("docker-compose.ec2.yml")["services"]
E2E_SERVICES = _compose("docker-compose.e2e.yml")["services"]
# Set by the image to its own copies; a host path in the settings files would replace them.
IMAGE_SET_KEYS = {"HFM_FRONTEND_DIST", "BUDGET_CONFIG"}
# Read from the process environment rather than by Settings.
ENVIRONMENT_KEYS = {"LANGGRAPH_STRICT_MSGPACK", f"{ENV_PREFIX}LOG_LEVEL", f"{ENV_PREFIX}LOG_LEVELS"}


def test_only_the_edge_and_the_database_publish_and_the_database_on_loopback() -> None:
    published = {name: spec["ports"] for name, spec in SERVICES.items() if "ports" in spec}
    assert published == {
        "db": [LOOPBACK + DB_PUBLISH],
        "edge": ["${EDGE_HOST_PORT:?set in stack-params.sh}:8010"],
    }


def test_the_end_to_end_file_publishes_only_amex_agent() -> None:
    published = {name: spec["ports"] for name, spec in E2E_SERVICES.items() if "ports" in spec}
    assert published == {"amex-agent": ["8020:8020"]}


def test_on_ec2_only_the_edge_is_published_at_the_origin_port() -> None:
    published = {name: spec["ports"] for name, spec in EC2_SERVICES.items() if "ports" in spec}
    assert published == {"edge": ["${EC2_ORIGIN_PORT:?set in stack-params.sh}:8010"]}


def test_no_service_mounts_a_file_of_this_machine() -> None:
    for name, spec in SERVICES.items():
        for volume in spec.get("volumes", []):
            assert volume.split(":")[0] in COMPOSE["volumes"], (name, volume)


def test_every_image_built_here_has_an_ec2_tag_for_arm() -> None:
    built = {name for name, spec in SERVICES.items() if "build" in spec}
    assert built == {"migrate", "manager", "edge"}
    for name in built:
        assert EC2_SERVICES[name]["image"].endswith(":ec2"), name
        assert EC2_SERVICES[name]["platform"] == "linux/arm64", name


def test_the_long_running_services_restart_on_ec2() -> None:
    restarting = {name for name, spec in EC2_SERVICES.items() if "restart" in spec}
    assert restarting == set(SERVICES) - {"migrate"}


def test_the_registry_reaches_the_manager_as_a_secret_of_each_target() -> None:
    assert COMPOSE["secrets"] == {"card-agents": {"environment": "CARD_AGENTS_REGISTRY"}}
    ec2 = _compose("docker-compose.ec2.yml")["secrets"]
    assert ec2 == {"card-agents": {"environment": "CARD_AGENTS_EC2_REGISTRY"}}
    manager = SERVICES["manager"]
    assert manager["secrets"] == ["card-agents"]
    assert manager["environment"]["CARD_AGENTS_FILE"] == "/run/secrets/card-agents"


def test_the_database_keeps_its_data_in_a_named_volume_and_reports_health() -> None:
    db = SERVICES["db"]
    assert db["image"] == "postgres:16"
    (volume,) = db["volumes"]
    assert volume.split(":")[0] in COMPOSE["volumes"]
    assert "pg_isready" in str(db["healthcheck"]["test"])


def test_the_migration_runs_once_from_the_manager_image_after_the_database() -> None:
    migrate = SERVICES["migrate"]
    assert migrate["command"] == "alembic upgrade head"
    assert migrate["image"] == SERVICES["manager"]["image"]
    assert migrate["depends_on"] == {"db": {"condition": "service_healthy"}}
    assert "restart" not in migrate


def test_the_network_address_overrides_the_host_form_of_the_database_url() -> None:
    for name in ("manager", "migrate"):
        assert "@db:${DB_PORT" in SERVICES[name]["environment"]["DATABASE_URL"], name


def test_each_container_receives_only_the_keys_it_reads() -> None:
    assert not [name for name, spec in SERVICES.items() if "env_file" in spec]
    settings_keys = {name.upper() for name in Settings.model_fields}
    manager_keys = (settings_keys - IMAGE_SET_KEYS) | ENVIRONMENT_KEYS
    assert set(SERVICES["manager"]["environment"]) == manager_keys
    assert set(SERVICES["migrate"]["environment"]) == {"DATABASE_URL"}


def test_the_database_user_and_name_come_from_the_settings_in_every_use() -> None:
    db = yaml.dump({"db": SERVICES["db"], "database": COMPOSE["x-database-env"]})
    assert "hfm" not in db.replace("hfm_pgdata", "")
