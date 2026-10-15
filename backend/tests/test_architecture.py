"""Runs the import-linter layer contracts declared in pyproject.toml as part of the test suite."""
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
# The console script is installed beside the interpreter running the tests, in the same venv.
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"


def test_import_contracts_hold():
    assert LINT_IMPORTS.is_file(), (
        f"{LINT_IMPORTS} not found; install the dev dependencies with pip install -e '.[dev]'"
    )
    # import-linter reads [tool.importlinter] from pyproject.toml in its working directory.
    result = subprocess.run(
        [LINT_IMPORTS], check=False, capture_output=True, text=True, cwd=BACKEND
    )
    assert result.returncode == 0, result.stdout + result.stderr
