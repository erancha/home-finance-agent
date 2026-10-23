"""Persistence ports for reviews, their event logs and the merchant-category memory.

Core building blocks:
- ReviewRepository: stores reviews, their status and when they were cleared; a person's month has
  at most one review that is not cleared
- ReviewEventStore: append-only per-review event log with sequence numbers
- MerchantMemory: merchant key to category lookups learned from each person's own choices
- ReportMemory: the report text each of a person's recent review prompts got

Every row belongs to one user, named by their Google account id.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from hfm.domain.events import ReviewEvent
from hfm.domain.models import Review, ReviewStatus


@runtime_checkable
class ReviewRepository(Protocol):
    async def add(self, review: Review) -> None:
        """Store a new review; raises ValueError when its id exists or the user's month already
        has a review that is not cleared."""
        ...

    async def get(self, review_id: str) -> Review:
        """Return the review; raises KeyError when the id is unknown."""
        ...

    async def set_status(self, review_id: str, status: ReviewStatus) -> None:
        """Replace the review's status; raises KeyError when the id is unknown."""
        ...

    async def list_by_status(self, status: ReviewStatus) -> list[Review]:
        """Return every review with the status, oldest first."""
        ...

    async def standing_for_month(self, user_id: str, month: str) -> Review | None:
        """Return the user's review of the month that is not cleared; None when there is none."""
        ...

    async def latest_completed_before(self, user_id: str, month: str) -> Review | None:
        """Return the user's completed review, not cleared, of the latest month before month;
        None when there is none."""
        ...

    async def list_created_since(self, user_id: str, since: datetime) -> list[Review]:
        """Return the user's reviews created at or after since, cleared or not, oldest first."""
        ...

    async def clear(self, review_id: str, at: datetime) -> None:
        """Record when the review was cleared; raises KeyError when the id is unknown."""
        ...


@runtime_checkable
class ReviewEventStore(Protocol):
    async def append(self, review_id: str, event: ReviewEvent) -> int:
        """Append the event and return its sequence number, 1-based per review."""
        ...

    async def list(self, review_id: str, after_seq: int = 0) -> list[tuple[int, ReviewEvent]]:
        """Return (sequence, event) pairs with sequence above after_seq, in order."""
        ...


@runtime_checkable
class MerchantMemory(Protocol):
    async def lookup(self, user_id: str, keys: Iterable[str]) -> dict[str, str]:
        """Return key to category for the keys the user has chosen before; others are omitted."""
        ...

    async def remember(self, user_id: str, key: str, category: str) -> None:
        """Store the user's category for the key, replacing any earlier one."""
        ...


@runtime_checkable
class ReportMemory(Protocol):
    async def lookup(self, user_id: str, prompt: str) -> str | None:
        """Return the text the user got for exactly this prompt; None when the memory holds none,
        including one written longer ago than the implementation's retention."""
        ...

    async def remember(self, user_id: str, month: str, prompt: str, text: str) -> None:
        """Store the text the prompt got for the user's review of the month, a prompt the memory
        does not hold; raises when it does. An implementation may forget the user's texts past
        its retention here, so reading costs nothing."""
        ...
