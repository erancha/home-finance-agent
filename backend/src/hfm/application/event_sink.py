"""Stamps each review event with its time, records it in the durable log, then fans it out to
live subscribers."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from hfm.domain.events import ReviewEvent
from hfm.ports import EventBus, ReviewEventStore


def review_channel(review_id: str) -> str:
    """The bus channel that carries one review's live events."""
    return f"review:{review_id}"


class ReviewEventSink:
    def __init__(
        self,
        store: ReviewEventStore,
        bus: EventBus,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._bus = bus
        self._now = now

    async def emit(self, review_id: str, event: ReviewEvent) -> None:
        """Persist before publishing so a subscriber never sees an event the log does not hold.

        The time travels in the data as at, so a replayed event shows when it happened.
        """
        stamped = ReviewEvent(
            event.type, {**event.data, "at": self._now().isoformat(timespec="seconds")}
        )
        seq = await self._store.append(review_id, stamped)
        await self._bus.publish(
            review_channel(review_id), {"type": stamped.type, "seq": seq, "data": stamped.data}
        )
