"""Review scenarios and app wiring shared by the platform tests."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession

from hfm.application.event_sink import ReviewEventSink
from hfm.application.review_graph import GraphDeps, build_review_graph, checkpoint_serde
from hfm.domain.errors import AgentUnusableError
from hfm.domain.events import REVIEW_FAILED, ReviewEvent
from hfm.domain.merchants import merchant_key
from hfm.domain.models import AgentConfig, Budget, TaskRef, Transaction, User
from hfm.platform.app import AppDeps
from hfm.ports import (
    SIGN_IN_REQUIRED,
    AgentEvent,
    AgentInfo,
    CardAgentClient,
    InputRequired,
    StatusEvent,
    TaskCompleted,
    TransactionsBatch,
)
from tests.builders import make_tx
from tests.fakes import (
    FakeReportWriter,
    FakeTokenVerifier,
    InMemoryEventBus,
    InMemoryLocks,
    InMemoryMerchantMemory,
    InMemoryReportMemory,
    InMemoryReviewEventStore,
    InMemoryReviewRepository,
    ScriptedCardAgentClient,
)

MONTH = "2026-09"
OTHER_MONTH = "2026-08"
DANA = User("1001", "dana@example.com", "Dana")
NOAM = User("1002", "noam@example.com", "Noam")
TOKENS = {"tok-dana": DANA, "tok-noam": NOAM}
"""The tokens the test verifier accepts and whom they name."""
DANA_TOKEN, NOAM_TOKEN = "tok-dana", "tok-noam"
AMEX = AgentConfig("amex", "http://amex.test", "token", "http://localhost:8020")
AMEX_INFO = AgentInfo("amex", "http://amex.test", True, ("monthly-transactions",))
TASK = TaskRef("amex", "t1", "c1")
BUDGET = Budget("ILS", {"groceries": Decimal(500)})
REPORT = "canned report"
EVENT_TIME = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
"""The time the test sink stamps on every event."""


def failed_event(message: str) -> ReviewEvent:
    return ReviewEvent(REVIEW_FAILED, {"message": message, "at": EVENT_TIME.isoformat()})

GROCERIES = make_tx(id="1", raw_merchant="שופרסל דיל", merchant="Shufersal", category="groceries")
UNKNOWN = make_tx(id="3")
UNKNOWN_KEY = merchant_key(UNKNOWN.raw_merchant)
CATEGORY_QUESTION = f"cat:{UNKNOWN_KEY}"
REMOTE_QUESTION = "remote:amex"
WORKING = StatusEvent("amex", "TASK_STATE_WORKING", "Reading statements")
COMPLETED = TaskCompleted("amex", TASK)
NEEDS_CODE = InputRequired("amex", TASK, "Enter the SMS code", "auth", MONTH, None)
SIGN_IN_AGAIN = InputRequired(
    "amex", TASK, "amex-agent could not verify who you are (expired).", SIGN_IN_REQUIRED, MONTH,
    None,
)


def batch(*transactions: Transaction) -> TransactionsBatch:
    return TransactionsBatch("amex", MONTH, transactions)


UNKNOWN_MERCHANT = [batch(GROCERIES, UNKNOWN), COMPLETED]
"""One fetch that leaves one merchant to categorize."""
UNKNOWN_MERCHANT_AND_CODE = [batch(GROCERIES, UNKNOWN), NEEDS_CODE]
"""One fetch that leaves a merchant to categorize and the agent waiting for a code."""


def scripted(*scripts: list[AgentEvent]) -> ScriptedCardAgentClient:
    return ScriptedCardAgentClient({"amex": AMEX_INFO}, {"amex": list(scripts)})


class BrokenCardClient:
    """Fails the way infrastructure does, with detail the user must not see."""

    async def discover(self, agent: AgentConfig) -> AgentInfo:
        raise ConnectionError("10.0.0.5:5432 refused for user hfm")

    async def fetch_month(
        self, agent: AgentConfig, month: str, resume: TaskRef | None, user_token: str
    ) -> AsyncIterator[AgentEvent]:
        raise AssertionError("fetch after a failed discovery")
        yield


class UnusableCardClient:
    async def discover(self, agent: AgentConfig) -> AgentInfo:
        raise AgentUnusableError(agent.name, "does not advertise the skill")

    async def fetch_month(
        self, agent: AgentConfig, month: str, resume: TaskRef | None, user_token: str
    ) -> AsyncIterator[AgentEvent]:
        raise AssertionError("fetch after a failed discovery")
        yield


class BlockedCardClient:
    """Discovery never returns, so a review using it stays running until cancelled."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.cancelled = False

    async def discover(self, agent: AgentConfig) -> AgentInfo:
        self.entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")

    async def fetch_month(
        self, agent: AgentConfig, month: str, resume: TaskRef | None, user_token: str
    ) -> AsyncIterator[AgentEvent]:
        raise AssertionError("fetch while discovery is blocked")
        yield


class UnreachableDatabase:
    """Session factory whose sessions fail the way an unreachable database does."""

    def __call__(self) -> AsyncSession:
        raise ConnectionRefusedError("database unreachable")


def app_deps(
    client: CardAgentClient,
    sessions: Any = None,
    card_agents: tuple[str, ...] = ("amex",),
    reviews: InMemoryReviewRepository | None = None,
) -> AppDeps:
    """App wiring over the given card client, in-memory fakes for the other ports and a review
    graph on an in-memory checkpointer; sessions default to an unreachable database, reviews to
    a fresh repository."""
    reviews = InMemoryReviewRepository() if reviews is None else reviews
    store = InMemoryReviewEventStore(reviews)
    bus = InMemoryEventBus()
    sink = ReviewEventSink(store, bus, lambda: EVENT_TIME)
    graph_deps = GraphDeps(
        client,
        InMemoryMerchantMemory(),
        BUDGET,
        FakeReportWriter(REPORT),
        InMemoryReportMemory(),
        sink,
        {"amex": AMEX},
    )
    graph = build_review_graph(graph_deps, InMemorySaver(serde=checkpoint_serde()))
    return AppDeps(
        reviews=reviews,
        events=store,
        bus=bus,
        sink=sink,
        graph=graph,
        locks=InMemoryLocks(),
        sessions=UnreachableDatabase() if sessions is None else sessions,
        verifier=FakeTokenVerifier(TOKENS),
        google_client_id="hfm-test-client",
        card_agents=card_agents,
    )
