"""Charges a review's month still expects, projected from the person's latest earlier review.

Core building blocks:
- expected_charges: the standing orders and next installments of the base month that the
  reviewed month has not charged yet
- with_expected: category totals with the expected spend added
- months_between: the distance between two YYYY-MM months

A mid-month review lacks the recurring charges its card agents have not billed yet; projecting
them from the base month lets the person see where the month is heading. An expected row keeps
the base row's amount and counted category, and its dates move forward by the months between.
"""
from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import replace
from datetime import date
from decimal import Decimal

from hfm.domain.merchants import merchant_key
from hfm.domain.models import CategoryTotal, Installment, Transaction
from hfm.domain.taxonomy import TAXONOMY

EXPECTED_ID_PREFIX = "expected-"
"""Keeps an expected row's id apart from the reviewed month's own ids of the same agent."""


def months_between(earlier: str, later: str) -> int:
    (from_year, from_month), (to_year, to_month) = _year_month(earlier), _year_month(later)
    return (to_year - from_year) * 12 + to_month - from_month


def expected_charges(
    base: Iterable[Transaction], base_month: str, charged: Iterable[Transaction], month: str
) -> list[Transaction]:
    """A base installment n of N expects payment n + gap while that is at most N; any other base
    standing order expects one charge. Either is dropped once the agent charged the merchant this
    month, an installment only by the payment number it expects."""
    gap = months_between(base_month, month)
    merchants = {_merchant(t) for t in charged}
    payments = {(_merchant(t), t.installment) for t in charged if t.installment is not None}
    expected: list[Transaction] = []
    for t in base:
        if t.installment is not None:
            due = Installment(t.installment.number + gap, t.installment.total)
            if due.number <= due.total and (_merchant(t), due) not in payments:
                expected.append(_moved(t, gap, due))
        elif t.standing_order and _merchant(t) not in merchants:
            expected.append(_moved(t, gap, None))
    return expected


def with_expected(
    actual: Iterable[CategoryTotal], expected: Iterable[Transaction]
) -> list[CategoryTotal]:
    """A category that only expected rows spend in has no limit: a budgeted one is in actual."""
    by_category = {t.category: t for t in actual}
    for t in expected:
        current = by_category.get(t.category, CategoryTotal(t.category, Decimal(0), None))
        by_category[t.category] = replace(current, spent=current.spent + t.amount)
    return [by_category[c] for c in TAXONOMY if c in by_category]


def _merchant(t: Transaction) -> tuple[str, str]:
    return (t.agent, merchant_key(t.raw_merchant))


def _moved(t: Transaction, gap: int, installment: Installment | None) -> Transaction:
    return replace(
        t,
        id=EXPECTED_ID_PREFIX + t.id,
        transaction_date=_add_months(t.transaction_date, gap),
        charge_date=_add_months(t.charge_date, gap),
        installment=installment,
    )


def _add_months(day: date, months: int) -> date:
    """The same day of the month, or the month's last day when it is shorter."""
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last))


def _year_month(month: str) -> tuple[int, int]:
    year, number = month.split("-")
    return int(year), int(number)
