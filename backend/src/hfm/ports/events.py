"""Port for publishing review events to live subscribers, keyed by channel."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventBus(Protocol):
    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        """Deliver the event to every current subscriber of the channel."""
        ...

    def subscribe(self, channel: str) -> AbstractAsyncContextManager[asyncio.Queue[dict[str, Any]]]:
        """Subscribe for the context duration; the queue receives events published meanwhile."""
        ...
