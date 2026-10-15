"""Value objects of the review: transactions, budgets, totals and review records.

Everything here is immutable; a transaction recategorized by the review is a new value
with the same identity key.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from hfm.domain.taxonomy import UNCATEGORIZED


@dataclass(frozen=True)
class Installment:
    number: int
    total: int


class Confidence(StrEnum):
    """How sure a card agent is of a row's category; it reports no score."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Transaction:
    id: str
    agent: str
    transaction_date: date
    charge_date: date
    merchant: str
    raw_merchant: str
    amount: Decimal
    original_amount: Decimal | None
    original_currency: str | None
    standing_order: bool
    abroad: bool
    installment: Installment | None
    category: str
    confidence: Confidence
    """The card agent's confidence in its own category; kept when the person overrules it."""
    chosen: bool = False
    """The category is the person's choice, which overrules the card agent's."""

    def with_category(self, category: str) -> Transaction:
        return replace(self, category=category, chosen=True)

    @property
    def unsure(self) -> bool:
        """The card agent could not place the row, or placed it with low confidence, and the
        person has not chosen its category."""
        return not self.chosen and (
            self.category == UNCATEGORIZED or self.confidence == Confidence.LOW
        )

    @property
    def key(self) -> tuple[str, str]:
        return (self.agent, self.id)


@dataclass(frozen=True)
class AgentConfig:
    name: str
    url: str
    """Where the home finance agent reaches the agent."""
    token: str
    browser_url: str
    """Where a person's browser reaches the agent, for links to the agent's own pages."""


@dataclass(frozen=True)
class TaskRef:
    agent: str
    task_id: str
    context_id: str


@dataclass(frozen=True)
class Budget:
    currency: str
    limits: dict[str, Decimal]


@dataclass(frozen=True)
class CategoryTotal:
    category: str
    spent: Decimal
    limit: Decimal | None

    @property
    def over(self) -> bool:
        return self.limit is not None and self.spent > self.limit


class ReviewStatus(StrEnum):
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class Review:
    id: str
    month: str
    status: ReviewStatus
    created_at: datetime
    cleared_at: datetime | None = None
    """When the person cleared the review to free its month for a new one; None while it stands."""
