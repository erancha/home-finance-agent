"""Card-agent client speaking A2A 1.0 over JSON-RPC with streaming, via the a2a-sdk.

Core building blocks:
- A2ACardAgentClient: discovers agent cards and streams month fetches as port events
- _translate: maps one A2A stream chunk (task snapshot, status, artifact) to agent events
- parse_transaction: maps one artifact row (camelCase JSON) to a domain Transaction

Each agent gets one HTTP client, card and A2A client, created on first use and kept until aclose;
a rediscovered card that differs replaces the A2A client. A garbled stream chunk or input request
raises AgentUnusableError naming the agent and what was wrong; a malformed transaction row raises
the KeyError or ValueError of its parse.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import aclosing
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from a2a.client import (
    A2ACardResolver,
    AgentCardResolutionError,
    Client,
    ClientConfig,
    ClientFactory,
)
from a2a.helpers import get_data_parts, get_text_parts, new_data_part, new_message
from a2a.types import AgentCard, Part, Role, SendMessageRequest, StreamResponse, TaskState
from a2a.utils.constants import TransportProtocol
from a2a.utils.errors import A2AError

from hfm.domain.errors import AgentUnusableError
from hfm.domain.models import AgentConfig, Confidence, Installment, TaskRef, Transaction
from hfm.domain.taxonomy import require_category
from hfm.ports.card_agent import (
    AgentEvent,
    AgentInfo,
    InputRequired,
    StatusEvent,
    TaskCompleted,
    TaskFailed,
    TransactionsBatch,
)

SKILL_ID = "monthly-transactions"

_FAILED_STATES = {
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
}

# Events after which the agent sends nothing more for this request; the agent closes the stream
# right after an input-required status even though that status is not flagged final.
_STREAM_ENDING_EVENTS = (InputRequired, TaskCompleted, TaskFailed)


# Read bounds the gap between stream events, which a real-model categorization run stretches.
HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)


def default_http(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=HTTP_TIMEOUT)


def default_client(card: AgentCard, http: httpx.AsyncClient) -> Client:
    return ClientFactory(ClientConfig(streaming=True, httpx_client=http)).create(card)


class A2ACardAgentClient:
    def __init__(
        self,
        http_factory: Callable[[str], httpx.AsyncClient] = default_http,
        client_factory: Callable[[AgentCard, httpx.AsyncClient], Any] = default_client,
    ) -> None:
        self._http_factory = http_factory
        self._client_factory = client_factory
        # Keys of all three maps: agent name
        self._http: dict[str, httpx.AsyncClient] = {}
        self._cards: dict[str, AgentCard] = {}
        self._clients: dict[str, Any] = {}

    async def discover(self, agent: AgentConfig) -> AgentInfo:
        try:
            card = await A2ACardResolver(self._http_for(agent), agent.url).get_agent_card()
        except AgentCardResolutionError as error:
            raise AgentUnusableError(agent.name, str(error)) from error
        skills = tuple(skill.id for skill in card.skills)
        if SKILL_ID not in skills:
            raise AgentUnusableError(
                agent.name, f"card does not advertise skill '{SKILL_ID}' (has {skills})"
            )
        interface_url = _jsonrpc_url(card)
        if interface_url is None:
            raise AgentUnusableError(agent.name, "card advertises no JSON-RPC interface")
        if not _declares_bearer(card):
            raise AgentUnusableError(agent.name, "card declares no HTTP bearer security scheme")
        if not agent.token:
            raise AgentUnusableError(agent.name, "card requires a bearer token but none is set")
        if self._cards.get(agent.name) != card:
            # The SDK client is bound to the card's interface URL; a changed card needs a new one.
            self._clients.pop(agent.name, None)
        self._cards[agent.name] = card
        return AgentInfo(
            name=agent.name,
            url=interface_url,
            streaming=card.capabilities.streaming,
            skills=skills,
        )

    async def fetch_month(
        self, agent: AgentConfig, month: str, resume: TaskRef | None
    ) -> AsyncIterator[AgentEvent]:
        client = await self._client_for(agent)
        stream = client.send_message(SendMessageRequest(message=_request_message(month, resume)))
        last_state = "no task state"
        try:
            async with aclosing(stream):
                async for chunk in stream:
                    for event in _translate(agent.name, chunk):
                        yield event
                        if isinstance(event, StatusEvent):
                            last_state = event.state
                        if isinstance(event, _STREAM_ENDING_EVENTS):
                            return
        except A2AError as error:
            yield TaskFailed(agent.name, str(error))
            return
        yield TaskFailed(
            agent.name, f"stream ended in {last_state} before the task finished or asked for input"
        )

    async def aclose(self) -> None:
        for http in self._http.values():
            await http.aclose()
        self._http.clear()
        self._cards.clear()
        self._clients.clear()

    def _http_for(self, agent: AgentConfig) -> httpx.AsyncClient:
        if agent.name not in self._http:
            self._http[agent.name] = self._http_factory(agent.token)
        return self._http[agent.name]

    async def _client_for(self, agent: AgentConfig) -> Any:
        if agent.name not in self._clients:
            if agent.name not in self._cards:
                await self.discover(agent)
            self._clients[agent.name] = self._client_factory(
                self._cards[agent.name], self._http_for(agent)
            )
        return self._clients[agent.name]


def _jsonrpc_url(card: AgentCard) -> str | None:
    """The URL the SDK's JSON-RPC transport calls, or None when the card offers no such binding."""
    urls = [
        interface.url
        for interface in card.supported_interfaces
        if interface.protocol_binding == TransportProtocol.JSONRPC and interface.url
    ]
    return urls[0] if urls else None


def _declares_bearer(card: AgentCard) -> bool:
    return any(
        scheme.HasField("http_auth_security_scheme")
        and scheme.http_auth_security_scheme.scheme.lower() == "bearer"
        for scheme in card.security_schemes.values()
    )


def _request_message(month: str, resume: TaskRef | None) -> Any:
    if resume is None:
        return new_message([new_data_part({"month": month})], role=Role.ROLE_USER)
    return new_message(
        [new_data_part({"action": "continue"})],
        role=Role.ROLE_USER,
        task_id=resume.task_id,
        context_id=resume.context_id,
    )


def _translate(agent: str, chunk: StreamResponse) -> list[AgentEvent]:
    if chunk.HasField("task"):
        # A snapshot can be the whole answer (e.g. resuming a task that already settled), so its
        # artifacts and status count exactly like streamed updates.
        task = chunk.task
        ref = TaskRef(agent=agent, task_id=task.id, context_id=task.context_id)
        batches = [b for artifact in task.artifacts for b in _batches(agent, artifact.parts)]
        return batches + _translate_status(agent, ref, task.status)
    if chunk.HasField("status_update"):
        update = chunk.status_update
        ref = TaskRef(agent=agent, task_id=update.task_id, context_id=update.context_id)
        return _translate_status(agent, ref, update.status)
    if chunk.HasField("artifact_update"):
        return list(_batches(agent, chunk.artifact_update.artifact.parts))
    if chunk.HasField("message"):
        reply = _text(chunk.message.parts)
        return [TaskFailed(agent, f"agent replied with a bare message instead of a task: {reply}")]
    raise AgentUnusableError(agent, "stream response carries no task, update or message")


def _batches(agent: str, parts: Sequence[Part]) -> list[TransactionsBatch]:
    return [
        TransactionsBatch(
            agent,
            data["month"],
            tuple(parse_transaction(agent, row) for row in data["transactions"]),
        )
        for data in get_data_parts(parts)
    ]


def _translate_status(agent: str, ref: TaskRef, status: Any) -> list[AgentEvent]:
    state = status.state
    parts = status.message.parts if status.HasField("message") else []
    text = _text(parts)
    events: list[AgentEvent] = [StatusEvent(agent, TaskState.Name(state), text)]
    if state == TaskState.TASK_STATE_INPUT_REQUIRED:
        if text is None:
            raise AgentUnusableError(agent, "asked for input without any text for the human")
        reason, month, page = _input_request(agent, parts)
        events.append(InputRequired(agent, ref, text, reason, month, page))
    elif state == TaskState.TASK_STATE_COMPLETED:
        events.append(TaskCompleted(agent, ref))
    elif state in _FAILED_STATES:
        events.append(TaskFailed(agent, text if text is not None else TaskState.Name(state)))
    return events


def _input_request(agent: str, parts: Sequence[Part]) -> tuple[str, str, str | None]:
    """The reason, month and optional page of an input-required status, all in one data part.

    The page must be a path on the agent's own origin, so a link built from it cannot lead
    anywhere else.
    """
    data = get_data_parts(parts)
    if len(data) != 1:
        raise AgentUnusableError(
            agent, f"asked for input with {len(data)} data parts instead of one"
        )
    missing = [key for key in ("reason", "month") if key not in data[0]]
    if missing:
        raise AgentUnusableError(
            agent, f"asked for input without {' and '.join(missing)} in its data part"
        )
    page = data[0].get("page")
    if page is not None and not (
        isinstance(page, str) and page.startswith("/") and not page.startswith("//")
    ):
        raise AgentUnusableError(agent, f"asked for input with page {page!r}, not a path")
    return data[0]["reason"], data[0]["month"], page


def _text(parts: Sequence[Part]) -> str | None:
    texts = get_text_parts(parts)
    return "\n".join(texts) if texts else None


def parse_transaction(agent: str, row: dict[str, Any]) -> Transaction:
    installment = row["installment"]
    original_amount = row["originalAmount"]
    return Transaction(
        id=row["id"],
        agent=agent,
        transaction_date=date.fromisoformat(row["transactionDate"]),
        charge_date=date.fromisoformat(row["chargeDate"]),
        merchant=row["merchant"],
        raw_merchant=row["rawMerchant"],
        amount=_decimal(row["amount"]),
        original_amount=_decimal(original_amount) if original_amount is not None else None,
        original_currency=row["originalCurrency"],
        standing_order=row["standingOrder"],
        abroad=row["abroad"],
        installment=(
            Installment(number=int(installment["number"]), total=int(installment["total"]))
            if installment is not None
            else None
        ),
        category=require_category(row["category"]),
        confidence=Confidence(row["confidence"]),
    )


def _decimal(value: float) -> Decimal:
    # Protobuf Struct carries JSON numbers as doubles; str() yields the shortest round-trip form.
    return Decimal(str(value))
