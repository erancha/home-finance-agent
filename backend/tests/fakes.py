"""In-memory test doubles that satisfy every port in hfm.ports.

Core building blocks:
- ScriptedCardAgentClient: replays scripted event sequences per agent and records its calls
- InMemoryReviewRepository, InMemoryReviewEventStore, InMemoryMerchantMemory,
  InMemoryReportMemory: dict-backed storage
- FakeTokenVerifier: maps known tokens to people, refuses the rest
- FakeReportWriter: returns fixed text and records prompts
- InMemoryEventBus: re-exported from the production adapter
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator, Iterable
from dataclasses import replace
from datetime import UTC, datetime

from hfm.adapters.memory_bus import InMemoryEventBus
from hfm.domain.errors import InvalidTokenError
from hfm.domain.events import ReviewEvent
from hfm.domain.models import (
    AgentConfig,
    Review,
    ReviewStatus,
    TaskRef,
    User,
    VerifiedToken,
)
from hfm.ports import AgentEvent, AgentInfo


class ScriptedCardAgentClient:
    """Each agent has a queue of event sequences; every fetch_month consumes the next one."""

    def __init__(
        self, infos: dict[str, AgentInfo], scripts: dict[str, list[list[AgentEvent]]]
    ) -> None:
        self._infos = infos
        self._scripts = scripts
        self.calls: list[tuple[str, str, TaskRef | None]] = []
        self.tokens: list[str] = []
        """The user token of each fetch, in call order."""

    async def discover(self, agent: AgentConfig) -> AgentInfo:
        return self._infos[agent.name]

    async def fetch_month(
        self, agent: AgentConfig, month: str, resume: TaskRef | None, user_token: str
    ) -> AsyncIterator[AgentEvent]:
        self.calls.append((agent.name, month, resume))
        self.tokens.append(user_token)
        queue = self._scripts.get(agent.name)
        if not queue:
            raise AssertionError(f"no scripted events left for agent {agent.name!r}")
        for event in queue.pop(0):
            yield event


class InMemoryReviewRepository:
    def __init__(self) -> None:
        self._reviews: dict[str, Review] = {}

    async def add(self, review: Review) -> None:
        if (
            review.id in self._reviews
            or await self.standing_for_month(review.user_id, review.month) is not None
        ):
            raise ValueError(
                f"review {review.id} or a standing review of {review.month} for user"
                f" {review.user_id} already exists"
            )
        self._reviews[review.id] = review

    async def get(self, review_id: str) -> Review:
        return self._reviews[review_id]

    def write_status(self, review_id: str, status: ReviewStatus) -> None:
        """Applies a status an event carries, for InMemoryReviewEventStore; not part of the port."""
        self._reviews[review_id] = replace(self._reviews[review_id], status=status)

    async def list_by_status(self, status: ReviewStatus) -> list[Review]:
        matching = [review for review in self._reviews.values() if review.status == status]
        return sorted(matching, key=lambda review: review.created_at)

    async def standing_for_month(self, user_id: str, month: str) -> Review | None:
        standing = [
            review
            for review in self._reviews.values()
            if review.user_id == user_id and review.month == month and review.cleared_at is None
        ]
        assert len(standing) <= 1, f"{month} has {len(standing)} standing reviews for {user_id}"
        return standing[0] if standing else None

    async def latest_completed_before(self, user_id: str, month: str) -> Review | None:
        earlier = [
            review
            for review in self._reviews.values()
            if review.user_id == user_id
            and review.month < month
            and review.status == ReviewStatus.COMPLETED
            and review.cleared_at is None
        ]
        return max(earlier, key=lambda review: review.month, default=None)

    async def list_created_since(self, user_id: str, since: datetime) -> list[Review]:
        recent = [
            review
            for review in self._reviews.values()
            if review.user_id == user_id and review.created_at >= since
        ]
        return sorted(recent, key=lambda review: review.created_at)

    async def clear(self, review_id: str, at: datetime) -> None:
        self._reviews[review_id] = replace(self._reviews[review_id], cleared_at=at)


class InMemoryReviewEventStore:
    """Writes the status an event carries into the given review repository, as the Postgres store
    does in the same transaction as the event."""

    def __init__(self, reviews: InMemoryReviewRepository) -> None:
        self._reviews = reviews
        self._events: dict[str, list[ReviewEvent]] = defaultdict(list)

    async def append(
        self, review_id: str, event: ReviewEvent, status: ReviewStatus | None = None
    ) -> int:
        if status is not None:
            self._reviews.write_status(review_id, status)
        events = self._events[review_id]
        events.append(event)
        return len(events)

    async def list(self, review_id: str, after_seq: int = 0) -> list[tuple[int, ReviewEvent]]:
        events = self._events[review_id]
        return [(seq, events[seq - 1]) for seq in range(after_seq + 1, len(events) + 1)]


class InMemoryMerchantMemory:
    def __init__(self) -> None:
        # Key: (user id, merchant key). Value: the category the user chose.
        self._categories: dict[tuple[str, str], str] = {}

    async def lookup(self, user_id: str, keys: Iterable[str]) -> dict[str, str]:
        return {
            key: self._categories[(user_id, key)]
            for key in keys
            if (user_id, key) in self._categories
        }

    async def remember(self, user_id: str, key: str, category: str) -> None:
        self._categories[(user_id, key)] = category


class InMemoryReportMemory:
    """Keeps every text for good; retention is the Postgres memory's concern."""

    def __init__(self) -> None:
        # Key: (user id, prompt). Value: the report text the prompt got.
        self._texts: dict[tuple[str, str], str] = {}

    async def lookup(self, user_id: str, prompt: str) -> str | None:
        return self._texts.get((user_id, prompt))

    async def remember(self, user_id: str, month: str, prompt: str, text: str) -> None:
        if (user_id, prompt) in self._texts:
            raise ValueError(f"user {user_id} already has a text for the prompt")
        self._texts[(user_id, prompt)] = text


class FakeTokenVerifier:
    """Accepts the tokens it was given, each naming a person; any other token is refused."""

    def __init__(self, tokens: dict[str, User], expires_at: datetime | None = None) -> None:
        self._tokens = tokens
        self._expires_at = expires_at or datetime(2099, 1, 1, tzinfo=UTC)

    def verify(self, token: str) -> VerifiedToken:
        if token not in self._tokens:
            raise InvalidTokenError("the token is not valid: unknown to the fake verifier")
        return VerifiedToken(self._tokens[token], self._expires_at)


class FakeReportWriter:
    def __init__(self, text: str = "canned report") -> None:
        self._text = text
        self.prompts: list[str] = []

    async def write(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._text

__all__ = [
    "FakeReportWriter",
    "FakeTokenVerifier",
    "InMemoryEventBus",
    "InMemoryMerchantMemory",
    "InMemoryReportMemory",
    "InMemoryReviewEventStore",
    "InMemoryReviewRepository",
    "ScriptedCardAgentClient",
]
