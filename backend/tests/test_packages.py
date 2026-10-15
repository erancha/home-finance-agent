"""Every hfm package imports cleanly."""
import importlib

import pytest

PACKAGES = ["hfm", "hfm.domain", "hfm.ports", "hfm.application", "hfm.adapters", "hfm.platform"]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_is_importable(name: str) -> None:
    assert importlib.import_module(name) is not None
