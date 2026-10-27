import asyncio
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from hfm.adapters.redis_bus import RedisEventBus
from hfm.ports import EventBus


@pytest.fixture
async def buses(redis_url: str) -> AsyncIterator[tuple[RedisEventBus, RedisEventBus]]:
    """Two buses on one Redis stand in for two agent replicas."""
    first, second = RedisEventBus(redis_url), RedisEventBus(redis_url)
    try:
        yield first, second
    finally:
        await first.aclose()
        await second.aclose()


async def test_the_bus_satisfies_the_port(redis_url: str) -> None:
    assert isinstance(RedisEventBus(redis_url), EventBus)


async def test_an_event_published_by_one_process_reaches_the_channels_subscribers_on_another(
    buses: tuple[RedisEventBus, RedisEventBus],
) -> None:
    publisher, subscriber = buses
    async with subscriber.subscribe("a") as queue_a, subscriber.subscribe("b") as queue_b:
        await publisher.publish("a", {"type": "review.report", "seq": 7, "data": {"text": "ok"}})
        received = await asyncio.wait_for(queue_a.get(), 5)
        assert received == {"type": "review.report", "seq": 7, "data": {"text": "ok"}}
        assert queue_b.empty()


async def test_a_subscription_is_live_before_the_context_body_runs(
    buses: tuple[RedisEventBus, RedisEventBus],
) -> None:
    """The event route subscribes, then replays the log, then reads live events; an event
    published between the subscribe and the replay must reach the queue."""
    publisher, subscriber = buses
    async with subscriber.subscribe("review:1") as queue:
        await publisher.publish("review:1", {"seq": 1})
        assert await asyncio.wait_for(queue.get(), 5) == {"seq": 1}


async def test_a_subscription_ends_with_its_context(
    redis_url: str, buses: tuple[RedisEventBus, RedisEventBus]
) -> None:
    _, subscriber = buses
    client = Redis.from_url(redis_url)
    try:
        async with subscriber.subscribe("ending"):
            assert await _subscriber_count(client, "ending") == 1
        # Leaving the context sends the unsubscribe without waiting for the server to apply it, so
        # a count read over another connection may lag by a moment.
        await _until_no_subscriber(client, "ending")
    finally:
        await client.aclose()


async def _subscriber_count(client: Redis, channel: str) -> int:
    [(_, count)] = await client.pubsub_numsub(channel)
    return int(count)


async def _until_no_subscriber(client: Redis, channel: str, deadline: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + deadline
    while await _subscriber_count(client, channel) != 0:
        assert loop.time() < end, f"{channel} still has a subscriber after {deadline}s"
        await asyncio.sleep(0.02)
