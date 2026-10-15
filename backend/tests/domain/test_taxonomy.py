"""The taxonomy matches the card agent's published list exactly."""
from __future__ import annotations

import pytest

from hfm.domain.taxonomy import TAXONOMY, UNCATEGORIZED, require_category


def test_taxonomy_is_the_published_list() -> None:
    assert TAXONOMY == (
        "groceries", "dining", "transport", "utilities", "housing", "health", "insurance",
        "education", "shopping", "entertainment", "travel", "gifts", "other",
        "uncategorized",
    )
    assert UNCATEGORIZED in TAXONOMY


def test_require_category_rejects_unknown() -> None:
    assert require_category("shopping") == "shopping"
    with pytest.raises(ValueError, match="pharmacy"):
        require_category("pharmacy")
