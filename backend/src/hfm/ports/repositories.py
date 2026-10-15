"""Persistence ports for reviews, their event logs and the merchant-category memory.

Core building blocks:
- ReviewRepository: stores reviews, their status and when they were cleared; a month has at most
  one review that is not cleared
- ReviewEventStore: append-only per-review event log with sequence numbers
- MerchantMemory: merchant key to category lookups learned from the person's choices
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
        """Store a new review; raises ValueError when its id exists or its month already has a
        review that is not cleared."""
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

    async def standing_for_month(self, month: str) -> Review | None:
        """Return the month's review that is not cleared; None when it has none."""
        ...

    async def list_created_since(self, since: datetime) -> list[Review]:
        """Return every review created at or after since, cleared or not, oldest first."""
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
    async def lookup(self, keys: Iterable[str]) -> dict[str, str]:
        """Return key to category for the known keys only; unknown keys are omitted."""
        ...

    async def remember(self, key: str, category: str) -> None:
        """Store the category for the key, replacing any earlier one."""
        ...
