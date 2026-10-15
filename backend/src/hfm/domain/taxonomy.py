"""The closed budget-category vocabulary shared with the card agents."""
from __future__ import annotations

TAXONOMY: tuple[str, ...] = (
    "groceries", "dining", "transport", "utilities", "housing", "health", "insurance", "education",
    "shopping", "entertainment", "travel", "gifts", "other", "uncategorized",
)

UNCATEGORIZED = "uncategorized"


def require_category(value: str) -> str:
    if value not in TAXONOMY:
        raise ValueError(
            f"'{value}' is not a budget category; expected one of {', '.join(TAXONOMY)}"
        )
    return value
