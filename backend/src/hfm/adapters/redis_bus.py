"""Event bus shared by every process of the agent through Redis publish/subscribe."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from redis.asyncio import Redis


class RedisEventBus:
    """Publishes on one shared client; each subscription holds a connection of its own, as Redis
    dedicates a connection to a subscriber. Events cross as JSON, so they must be JSON-safe."""

    def __init__(self, url: str) -> None:
        self._client = Redis.from_url(url)

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        await self._client.publish(channel, json.dumps(event))

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)
        messages = pubsub.listen()
        # Redis confirms the subscription before it delivers on it, so once the confirmation has
        # arrived every later publish reaches the queue: the event route counts on that when it
        # subscribes before replaying the log.
        confirmation = await anext(messages)
        assert confirmation["type"] == "subscribe", confirmation
        forwarding = asyncio.create_task(_forward(messages, queue))
        try:
            yield queue
        finally:
            forwarding.cancel()
            await asyncio.gather(forwarding, return_exceptions=True)
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()


async def _forward(messages: AsyncIterator[Any], queue: asyncio.Queue[dict[str, Any]]) -> None:
    async for message in messages:
        if message["type"] == "message":
            queue.put_nowait(json.loads(message["data"]))
