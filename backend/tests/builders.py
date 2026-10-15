"""Test data builders shared across test packages."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from hfm.domain.models import Confidence, Transaction
from hfm.domain.taxonomy import UNCATEGORIZED


def make_tx(**overrides: Any) -> Transaction:
    base: dict[str, Any] = {
        "id": "201939841",
        "agent": "amex",
        "transaction_date": date(2026, 9, 5),
        "charge_date": date(2026, 10, 2),
        "merchant": "Super-Pharm",
        "raw_merchant": "סופר פארם בעמ 123",
        "amount": Decimal("86.90"),
        "original_amount": None,
        "original_currency": None,
        "standing_order": False,
        "abroad": False,
        "installment": None,
        "category": "uncategorized",
    }
    base.update(overrides)
    # A categorized row defaults to the agent being sure of it; an uncategorized one is low.
    base.setdefault(
        "confidence",
        Confidence.LOW if base["category"] == UNCATEGORIZED else Confidence.HIGH,
    )
    return Transaction(**base)
