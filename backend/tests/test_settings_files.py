"""Checks that the settings files document exactly the keys the agent and its compose services read.

The settings live in three files under scripts/lib/: the committed stack-params.sh, and
params.example.sh and secrets.example.sh, which init-env.sh copies to the gitignored params.sh
and secrets.sh. A key counts as documented when a line of one of them assigns it, commented out
or not (export KEY="value" or # export KEY="value"). Every documented key is a Settings field or a
key that only compose, the logging setup, the settings guard or the EC2 scripts read. Unfilled
copies of the examples must not start the agent, and scripts/init-env.sh must fill in every key it
owns, leaving only LLM_MODEL, LLM_API_KEY and GOOGLE_CLIENT_ID for the person.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from hfm.platform.config import SETTINGS_FILES, Settings
from hfm.platform.logging import ENV_PREFIX

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "scripts" / "lib"
STACK_PARAMS = LIB / "stack-params.sh"
EXAMPLES = (LIB / "params.example.sh", LIB / "secrets.example.sh")
SCRIPTS = REPO / "scripts"

COMPOSE_ONLY_KEYS = {
    "EDGE_HOST_PORT",
    "DB_PORT",
    "DB_HOST_PORT",
    "POSTGRES_USER",
    "POSTGRES_DB",
    "POSTGRES_PASSWORD",
}
# Read by hfm.platform.logging.configure_logging from the process environment.
LOGGING_KEYS = {f"{ENV_PREFIX}LOG_LEVEL", f"{ENV_PREFIX}LOG_LEVELS"}
# Read by scripts/lib/settings-guard.sh only: the address tracked files may show.
GUARD_ONLY_KEYS = {"LICENSE_CONTACT"}
# Read by scripts/lib/ec2.sh only, for deploy.sh --ec2.
EC2_ONLY_KEYS = {"EC2_STACK", "EC2_HOST_STACK", "EC2_ORIGIN_PORT"}
NOT_SETTINGS_KEYS = COMPOSE_ONLY_KEYS | LOGGING_KEYS | GUARD_ONLY_KEYS | EC2_ONLY_KEYS

_ASSIGNMENT = re.compile(r"^(?:#\s*)?export ([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def _documented_keys() -> set[str]:
    text = "".join(path.read_text(encoding="utf-8") for path in (STACK_PARAMS, *EXAMPLES))
    return set(_ASSIGNMENT.findall(text))


def _settings_keys() -> set[str]:
    return {name.upper() for name in Settings.model_fields}


def _exported_by(*files: Path) -> dict[str, str]:
    """The variables a shell holds after sourcing the files in order, as the scripts do."""
    sources = "; ".join(f'source "{path}"' for path in files)
    output = subprocess.run(
        ["bash", "-c", f"{sources}; env -0"], check=True, capture_output=True, env={}
    ).stdout.decode()
    return dict(entry.split("=", 1) for entry in output.split("\0") if "=" in entry)


def test_the_settings_files_are_the_ones_the_agent_reads() -> None:
    assert [REPO / name for name in SETTINGS_FILES] == [
        STACK_PARAMS,
        LIB / "params.sh",
        LIB / "secrets.sh",
    ]


def test_every_settings_field_is_documented() -> None:
    missing = sorted(_settings_keys() - _documented_keys())
    assert not missing, f"Settings fields missing from the settings files: {missing}"


def test_every_key_only_other_readers_take_is_documented() -> None:
    assert NOT_SETTINGS_KEYS <= _documented_keys()


def test_no_documented_key_is_unknown() -> None:
    unknown = sorted(_documented_keys() - _settings_keys() - NOT_SETTINGS_KEYS)
    assert not unknown, f"The settings files document keys nothing reads: {unknown}"


def test_no_secret_is_committed_in_the_stack_parameters() -> None:
    committed = set(_ASSIGNMENT.findall(STACK_PARAMS.read_text(encoding="utf-8")))
    secret = {
        name.upper()
        for name, field in Settings.model_fields.items()
        if "SecretStr" in str(field.annotation)
    } | {"POSTGRES_PASSWORD"}
    assert not committed & secret


def test_unfilled_copies_do_not_start(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _exported_by(STACK_PARAMS, *EXAMPLES).items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError) as error:
        Settings()  # type: ignore[call-arg]
    failed = {e["loc"][0] for e in error.value.errors()}
    assert failed == {"database_url", "google_client_id"}


def test_init_env_writes_the_settings_it_owns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    for folder in ("scripts/lib", "backend", "config"):
        (root / folder).mkdir(parents=True)
    for script in ("common.sh", "init-env.sh"):
        shutil.copy(SCRIPTS / script, root / "scripts" / script)
    for path in (
        STACK_PARAMS,
        LIB / "settings-guard.sh",
        LIB / "ec2.sh",
        LIB / "aws-config.example.sh",
        *EXAMPLES,
    ):
        shutil.copy(path, root / "scripts" / "lib" / path.name)
    shutil.copy(REPO / "config" / "budget.example.yaml", root / "config")
    subprocess.run([str(root / "scripts" / "init-env.sh")], check=True, capture_output=True)
    created = [root / name for name in SETTINGS_FILES]
    for path in created[1:]:
        assert path.stat().st_mode & 0o077 == 0, path.name
    env = _exported_by(*created)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # The keys init-env.sh leaves for the person to supply.
    for key, value in {
        "LLM_MODEL": "anthropic:claude-haiku-5-5",
        "LLM_API_KEY": "sk-test",
        "GOOGLE_CLIENT_ID": "1-a.apps.googleusercontent.com",
    }.items():
        monkeypatch.setenv(key, value)
    settings = Settings()  # type: ignore[call-arg]
    password = env["POSTGRES_PASSWORD"]
    assert len(password) == 32
    assert settings.database_url.get_secret_value() == (
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{password}"
        f"@127.0.0.1:{env['DB_HOST_PORT']}/{env['POSTGRES_DB']}"
    )
