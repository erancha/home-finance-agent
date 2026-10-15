"""In-memory test doubles that satisfy every port in hfm.ports.

Core building blocks:
- ScriptedCardAgentClient: replays scripted event sequences per agent and records its calls
- InMemoryReviewRepository, InMemoryReviewEventStore, InMemoryMerchantMemory: dict-backed storage
- FakeReportWriter: returns fixed text and records prompts
- InMemoryEventBus: re-exported from the production adapter
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator, Iterable
from dataclasses import replace
from datetime import datetime

from hfm.adapters.memory_bus import InMemoryEventBus
from hfm.domain.events import ReviewEvent
from hfm.domain.models import AgentConfig, Review, ReviewStatus, TaskRef
from hfm.ports import AgentEvent, AgentInfo


class ScriptedCardAgentClient:
    """Each agent has a queue of event sequences; every fetch_month consumes the next one."""

    def __init__(
        self, infos: dict[str, AgentInfo], scripts: dict[str, list[list[AgentEvent]]]
    ) -> None:
        self._infos = infos
        self._scripts = scripts
        self.calls: list[tuple[str, str, TaskRef | None]] = []

    async def discover(self, agent: AgentConfig) -> AgentInfo:
        return self._infos[agent.name]

    async def fetch_month(
        self, agent: AgentConfig, month: str, resume: TaskRef | None
    ) -> AsyncIterator[AgentEvent]:
        self.calls.append((agent.name, month, resume))
        queue = self._scripts.get(agent.name)
        if not queue:
            raise AssertionError(f"no scripted events left for agent {agent.name!r}")
        for event in queue.pop(0):
            yield event


class InMemoryReviewRepository:
    def __init__(self) -> None:
        self._reviews: dict[str, Review] = {}

    async def add(self, review: Review) -> None:
        if review.id in self._reviews or await self.standing_for_month(review.month) is not None:
            raise ValueError(
                f"review {review.id} or a standing review of {review.month} already exists"
            )
        self._reviews[review.id] = review

    async def get(self, review_id: str) -> Review:
        return self._reviews[review_id]

    async def set_status(self, review_id: str, status: ReviewStatus) -> None:
        self._reviews[review_id] = replace(self._reviews[review_id], status=status)

    async def list_by_status(self, status: ReviewStatus) -> list[Review]:
        matching = [review for review in self._reviews.values() if review.status == status]
        return sorted(matching, key=lambda review: review.created_at)

    async def standing_for_month(self, month: str) -> Review | None:
        standing = [
            review
            for review in self._reviews.values()
            if review.month == month and review.cleared_at is None
        ]
        assert len(standing) <= 1, f"{month} has {len(standing)} standing reviews"
        return standing[0] if standing else None

    async def list_created_since(self, since: datetime) -> list[Review]:
        recent = [review for review in self._reviews.values() if review.created_at >= since]
        return sorted(recent, key=lambda review: review.created_at)

    async def clear(self, review_id: str, at: datetime) -> None:
        self._reviews[review_id] = replace(self._reviews[review_id], cleared_at=at)


class InMemoryReviewEventStore:
    def __init__(self) -> None:
        self._events: dict[str, list[ReviewEvent]] = defaultdict(list)

    async def append(self, review_id: str, event: ReviewEvent) -> int:
        events = self._events[review_id]
        events.append(event)
        return len(events)

    async def list(self, review_id: str, after_seq: int = 0) -> list[tuple[int, ReviewEvent]]:
        events = self._events[review_id]
        return [(seq, events[seq - 1]) for seq in range(after_seq + 1, len(events) + 1)]


class InMemoryMerchantMemory:
    def __init__(self) -> None:
        self._categories: dict[str, str] = {}

    async def lookup(self, keys: Iterable[str]) -> dict[str, str]:
        return {key: self._categories[key] for key in keys if key in self._categories}

    async def remember(self, key: str, category: str) -> None:
        self._categories[key] = category


class FakeReportWriter:
    def __init__(self, text: str = "canned report") -> None:
        self._text = text
        self.prompts: list[str] = []

    async def write(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._text

__all__ = [
    "FakeReportWriter",
    "InMemoryEventBus",
    "InMemoryMerchantMemory",
    "InMemoryReviewEventStore",
    "InMemoryReviewRepository",
    "ScriptedCardAgentClient",
]
