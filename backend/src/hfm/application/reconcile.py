"""Pure arithmetic of the review: transaction merging, merchant memory and budget totals.

Core building blocks:
- merge_transactions / merge_dict: reducers that merge node results into the review state
- apply_memory / unsure_merchants: merchant-level categorisation
- totals: per-category spend against the budget
- standing_orders: the spend charged by standing order, whatever its category
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from hfm.domain.merchants import merchant_key
from hfm.domain.models import Budget, CategoryTotal, Transaction
from hfm.domain.taxonomy import TAXONOMY, require_category


def merge_transactions(existing: list[Transaction], new: list[Transaction]) -> list[Transaction]:
    """Later value wins per (agent, id); first-seen order is kept."""
    merged: dict[tuple[str, str], Transaction] = {}
    for t in [*existing, *new]:
        merged[t.key] = t
    return list(merged.values())


def merge_dict(existing: dict[Any, Any], new: dict[Any, Any]) -> dict[Any, Any]:
    """A None value in new removes the key."""
    merged = {**existing, **new}
    return {k: v for k, v in merged.items() if v is not None}


def apply_memory(transactions: Iterable[Transaction], memory: dict[str, str]) -> list[Transaction]:
    """A category the user chose for a merchant outranks the card agent's own category."""
    return [_remembered(t, memory) for t in transactions]


def _remembered(t: Transaction, memory: dict[str, str]) -> Transaction:
    key = merchant_key(t.raw_merchant)
    return t.with_category(memory[key]) if key in memory else t


def unsure_merchants(
    transactions: Iterable[Transaction],
) -> dict[str, tuple[Transaction, ...]]:
    """Merchant key to the rows its card agent was unsure of, in arrival order."""
    rows: dict[str, list[Transaction]] = {}
    for t in transactions:
        if t.unsure:
            rows.setdefault(merchant_key(t.raw_merchant), []).append(t)
    return {key: tuple(found) for key, found in rows.items()}


def totals(transactions: Iterable[Transaction], budget: Budget) -> list[CategoryTotal]:
    spent: dict[str, Decimal] = {}
    for t in transactions:
        spent[t.category] = spent.get(t.category, Decimal(0)) + t.amount
    for category in spent:
        require_category(category)
    return [
        CategoryTotal(c, spent.get(c, Decimal(0)), budget.limits.get(c))
        for c in TAXONOMY
        if c in spent or c in budget.limits
    ]


def standing_orders(transactions: Iterable[Transaction]) -> Decimal:
    return sum((t.amount for t in transactions if t.standing_order), Decimal(0))
