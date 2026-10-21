"""Port to the card agents that supply monthly transactions.

Core building blocks:
- AgentInfo: what discovery reveals about a card agent
- Agent events: the stream a month fetch yields (status, batches, input requests, terminal states)
- CardAgentClient: discovery plus the streaming month fetch, made on behalf of a signed-in person
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from hfm.domain.models import AgentConfig, TaskRef, Transaction


@dataclass(frozen=True)
class AgentInfo:
    """A usable agent's card; discovery refuses a card that lacks the monthly-transactions skill,
    a JSON-RPC interface or an HTTP bearer scheme."""

    name: str
    url: str
    streaming: bool
    skills: tuple[str, ...]


@dataclass(frozen=True)
class StatusEvent:
    agent: str
    state: str
    text: str | None


@dataclass(frozen=True)
class TransactionsBatch:
    agent: str
    month: str
    transactions: tuple[Transaction, ...]


SIGN_IN_REQUIRED = "sign-in-required"
"""Reason of an InputRequired raised because the agent could not verify the person's token; the
person signs in again and continues, and the continue carries the fresh token."""


@dataclass(frozen=True)
class InputRequired:
    agent: str
    task: TaskRef
    text: str
    reason: str
    """The agent's reason, such as statement-missing or SIGN_IN_REQUIRED."""
    month: str
    page: str | None
    """Path on the agent's own origin of a page where a person resolves the request; None when
    the agent offers no such page."""


@dataclass(frozen=True)
class TaskCompleted:
    agent: str
    task: TaskRef


@dataclass(frozen=True)
class TaskFailed:
    agent: str
    message: str


AgentEvent = StatusEvent | TransactionsBatch | InputRequired | TaskCompleted | TaskFailed


@runtime_checkable
class CardAgentClient(Protocol):
    async def discover(self, agent: AgentConfig) -> AgentInfo:
        """Return the agent's advertised capabilities; raises if the agent is unreachable or its
        card is unusable."""
        ...

    def fetch_month(
        self, agent: AgentConfig, month: str, resume: TaskRef | None, user_token: str
    ) -> AsyncIterator[AgentEvent]:
        """Stream the events of one month fetch, ending with TaskCompleted or TaskFailed.

        A non-None resume continues the task of an earlier InputRequired instead of starting anew.
        user_token is the signed-in person's ID token, forwarded so the agent serves their data.
        """
        ...
