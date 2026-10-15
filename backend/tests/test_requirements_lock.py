"""Guards the backend dependency lockfile against drift.

The Docker image must install pinned versions from requirements.txt (compiled from
pyproject.toml) so image builds are reproducible. These checks fail when a direct runtime
dependency is added to pyproject.toml without regenerating the lock, or when the Dockerfile
stops installing from it.
"""
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

BACKEND = Path(__file__).resolve().parents[1]
LOCKFILE = BACKEND / "requirements.txt"


def _direct_runtime_dependencies() -> set[str]:
    pyproject = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        canonicalize_name(Requirement(spec).name)
        for spec in pyproject["project"]["dependencies"]
    }


def _locked_pins() -> dict[str, str]:
    # Key: canonical package name  Value: the version specifier it was pinned with
    pins: dict[str, str] = {}
    for line in LOCKFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        requirement = Requirement(line)
        pins[canonicalize_name(requirement.name)] = str(requirement.specifier)
    return pins


def test_lockfile_pins_every_direct_runtime_dependency():
    assert LOCKFILE.exists(), "backend/requirements.txt lockfile is missing"
    pins = _locked_pins()
    for name in sorted(_direct_runtime_dependencies()):
        assert name in pins, f"{name} is in pyproject.toml but not in requirements.txt"
        assert pins[name].startswith("=="), f"{name} is not pinned exactly: {pins[name]}"


def test_dockerfile_installs_from_lockfile():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert "requirements.txt" in dockerfile, (
        "Dockerfile does not install dependencies from the requirements.txt lockfile"
    )
