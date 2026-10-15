import asyncio

from hfm.adapters.memory_bus import InMemoryEventBus


async def test_published_event_reaches_only_subscribers_of_the_channel() -> None:
    bus = InMemoryEventBus()
    async with bus.subscribe("a") as queue_a, bus.subscribe("b") as queue_b:
        await bus.publish("a", {"n": 1})
        assert await asyncio.wait_for(queue_a.get(), 1) == {"n": 1}
        assert queue_b.empty()


async def test_subscription_ends_with_the_context() -> None:
    bus = InMemoryEventBus()
    async with bus.subscribe("a"):
        assert bus.subscriber_count("a") == 1
    assert bus.subscriber_count("a") == 0
