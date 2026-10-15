"""Event bus for a single process: subscribers receive events through per-subscription queues."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


class InMemoryEventBus:
    def __init__(self) -> None:
        self._subscriptions: set[tuple[str, asyncio.Queue[dict[str, Any]]]] = set()

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        for subscribed_channel, queue in list(self._subscriptions):
            if subscribed_channel == channel:
                queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        subscription = (channel, queue)
        self._subscriptions.add(subscription)
        try:
            yield queue
        finally:
            self._subscriptions.discard(subscription)

    def subscriber_count(self, channel: str) -> int:
        return sum(
            1 for subscribed_channel, _ in self._subscriptions if subscribed_channel == channel
        )
