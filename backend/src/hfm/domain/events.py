"""Progress events streamed to the UI while a review runs."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from hfm.domain.merchants import merchant_key
from hfm.domain.models import CategoryTotal, Transaction

AGENT_DISCOVERED = "agent.discovered"
AGENT_STATUS = "agent.status"
TRANSACTIONS_BATCH = "transactions.batch"
REVIEW_QUESTION = "review.question"
REVIEW_TOTALS = "review.totals"
REVIEW_REPORT = "review.report"
REVIEW_FAILED = "review.failed"


@dataclass(frozen=True)
class ReviewEvent:
    type: str
    data: dict[str, Any]


CENTS = Decimal("0.01")


def money_text(amount: Decimal) -> str:
    """An amount in the budget currency as text with two decimal places; arithmetic stays exact."""
    return str(amount.quantize(CENTS))


def transaction_to_dict(t: Transaction) -> dict[str, Any]:
    return {
        "id": t.id,
        "agent": t.agent,
        "transactionDate": t.transaction_date.isoformat(),
        "chargeDate": t.charge_date.isoformat(),
        "merchant": t.merchant,
        "rawMerchant": t.raw_merchant,
        "merchantKey": merchant_key(t.raw_merchant),
        "amount": money_text(t.amount),
        # A foreign currency's minor unit need not be two places, so its amount is kept as sent.
        "originalAmount": None if t.original_amount is None else str(t.original_amount),
        "originalCurrency": t.original_currency,
        "standingOrder": t.standing_order,
        "abroad": t.abroad,
        "installment": (
            None if t.installment is None
            else {"number": t.installment.number, "total": t.installment.total}
        ),
        "category": t.category,
        "confidence": t.confidence,
    }


def total_to_dict(t: CategoryTotal) -> dict[str, Any]:
    return {
        "category": t.category,
        "spent": money_text(t.spent),
        "limit": None if t.limit is None else money_text(t.limit),
        "over": t.over,
    }
