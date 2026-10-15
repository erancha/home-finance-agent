"""Checks that each fake satisfies its port and behaves as the application relies on."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from hfm.domain.events import ReviewEvent
from hfm.domain.models import AgentConfig, Review, ReviewStatus, TaskRef
from hfm.ports import (
    AgentInfo,
    CardAgentClient,
    EventBus,
    MerchantMemory,
    ReportWriter,
    ReviewEventStore,
    ReviewRepository,
    StatusEvent,
    TaskCompleted,
)
from tests.fakes import (
    FakeReportWriter,
    InMemoryEventBus,
    InMemoryMerchantMemory,
    InMemoryReviewEventStore,
    InMemoryReviewRepository,
    ScriptedCardAgentClient,
)

AGENT = AgentConfig("isracard", "http://agent", "t", "http://agent")
INFO = AgentInfo(name="isracard", url="http://agent", streaming=True, skills=("fetch",))
TASK = TaskRef(agent="isracard", task_id="t1", context_id="c1")


def test_fakes_satisfy_their_ports() -> None:
    assert isinstance(ScriptedCardAgentClient({}, {}), CardAgentClient)
    assert isinstance(InMemoryReviewRepository(), ReviewRepository)
    assert isinstance(InMemoryReviewEventStore(), ReviewEventStore)
    assert isinstance(InMemoryMerchantMemory(), MerchantMemory)
    assert isinstance(FakeReportWriter(), ReportWriter)
    assert isinstance(InMemoryEventBus(), EventBus)


async def test_event_store_sequences_per_review_and_lists_after_seq() -> None:
    store = InMemoryReviewEventStore()
    first, second = ReviewEvent("a", {}), ReviewEvent("b", {})
    assert await store.append("r1", first) == 1
    assert await store.append("r1", second) == 2
    assert await store.append("r2", first) == 1
    assert await store.list("r1") == [(1, first), (2, second)]
    assert await store.list("r1", after_seq=1) == [(2, second)]


async def test_review_repository_refuses_a_duplicate_id_and_keeps_the_original() -> None:
    reviews = InMemoryReviewRepository()
    original = Review("r1", "2026-09", ReviewStatus.RUNNING, datetime(2026, 10, 1, tzinfo=UTC))
    await reviews.add(original)

    with pytest.raises(ValueError, match="r1"):
        await reviews.add(replace(original, month="2026-08"))
    assert await reviews.get("r1") == original


async def test_merchant_memory_returns_known_keys_and_upserts() -> None:
    memory = InMemoryMerchantMemory()
    await memory.remember("shufersal", "groceries")
    assert await memory.lookup(["shufersal", "unknown"]) == {"shufersal": "groceries"}
    await memory.remember("shufersal", "other")
    assert await memory.lookup(["shufersal"]) == {"shufersal": "other"}


async def test_report_writer_records_prompts() -> None:
    writer = FakeReportWriter("hello")
    assert await writer.write("p1") == "hello"
    assert writer.prompts == ["p1"]


async def test_bus_delivers_only_to_subscribers_of_the_channel() -> None:
    bus = InMemoryEventBus()
    async with bus.subscribe("r1") as queue, bus.subscribe("r2") as other:
        await bus.publish("r1", {"n": 1})
        assert queue.get_nowait() == {"n": 1}
        assert other.empty()
        assert bus.subscriber_count("r1") == 1
    assert bus.subscriber_count("r1") == 0
    assert bus.subscriber_count("r2") == 0


async def test_scripted_client_pops_scripts_in_order_and_records_calls() -> None:
    first = [StatusEvent("isracard", "working", None)]
    second = [TaskCompleted("isracard", TASK)]
    client = ScriptedCardAgentClient({"isracard": INFO}, {"isracard": [first, second]})
    assert await client.discover(AGENT) == INFO
    assert [e async for e in client.fetch_month(AGENT, "2026-09", None)] == first
    assert [e async for e in client.fetch_month(AGENT, "2026-09", TASK)] == second
    assert client.calls == [("isracard", "2026-09", None), ("isracard", "2026-09", TASK)]


async def test_scripted_client_fails_loudly_when_exhausted() -> None:
    client = ScriptedCardAgentClient({}, {"isracard": []})
    with pytest.raises(AssertionError, match="isracard"):
        [e async for e in client.fetch_month(AGENT, "2026-09", None)]
