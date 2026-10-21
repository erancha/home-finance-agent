"""Card-agent client speaking A2A 1.0 over JSON-RPC with streaming, via the a2a-sdk.

Core building blocks:
- A2ACardAgentClient: discovers agent cards and streams month fetches as port events, each call
  carrying the person's ID token as the bearer and the caller secret under the header the card
  names
- _credential_header: reads the card's security schemes, which must ask for both credentials
- _translate: maps one A2A stream chunk (task snapshot, status, artifact) to agent events
- parse_transaction: maps one artifact row (camelCase JSON) to a domain Transaction

Each agent gets one HTTP client, card and A2A client, created on first use and kept until aclose;
a rediscovered card that differs replaces the A2A client. Credentials never sit on the HTTP
client: they are per call, since one client serves every person's reviews. A garbled stream chunk
or input request raises AgentUnusableError naming the agent and what was wrong; a malformed
transaction row raises the KeyError or ValueError of its parse. A refused or dropped connection
and a refused secret are reported in words for the person, with the sdk's error in the log.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import aclosing
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import httpx
import structlog
from a2a.client import (
    A2ACardResolver,
    AgentCardResolutionError,
    Client,
    ClientCallContext,
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
    SIGN_IN_REQUIRED,
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

# States in which the agent waits for the person, and how a fault in them is named.
_PAUSED_STATES = {
    TaskState.TASK_STATE_INPUT_REQUIRED: "asked for input",
    TaskState.TASK_STATE_AUTH_REQUIRED: "asked for sign-in",
}


# Read bounds the gap between stream events, which a real-model categorization run stretches.
HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)

log = structlog.get_logger(__name__)


def _unreachable(url: str) -> str:
    return f"could not be reached at {url}; it may not be running"


def _unreachable_call(agent: AgentConfig, called: str) -> str:
    """The A2A call goes to the address the card advertises, which an operator may not expect
    when it differs from the registered one, so that case names both."""
    if urlsplit(called).netloc == urlsplit(agent.url).netloc:
        return _unreachable(called)
    return (f"could not be reached at {called}, the address its card advertises "
            f"(registered at {agent.url}); it may not be running")


# The sdk chains the httpx failure it wraps as the cause of its own error.
def _connection_lost(error: BaseException) -> bool:
    return isinstance(error.__cause__, httpx.RequestError)


def _refused_secret(error: BaseException) -> bool:
    cause = error.__cause__
    return isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 401


def default_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT)


def default_client(card: AgentCard, http: httpx.AsyncClient) -> Client:
    return ClientFactory(ClientConfig(streaming=True, httpx_client=http)).create(card)


class A2ACardAgentClient:
    def __init__(
        self,
        http_factory: Callable[[], httpx.AsyncClient] = default_http,
        client_factory: Callable[[AgentCard, httpx.AsyncClient], Any] = default_client,
    ) -> None:
        self._http_factory = http_factory
        self._client_factory = client_factory
        # Keys of all four maps: agent name
        self._http: dict[str, httpx.AsyncClient] = {}
        self._cards: dict[str, AgentCard] = {}
        self._clients: dict[str, Any] = {}
        self._secret_headers: dict[str, str] = {}
        """The header the agent's card names for the caller secret."""

    async def discover(self, agent: AgentConfig) -> AgentInfo:
        try:
            card = await A2ACardResolver(self._http_for(agent), agent.url).get_agent_card()
        except AgentCardResolutionError as error:
            log.warning("card fetch failed", agent=agent.name, url=agent.url, error=str(error))
            if _connection_lost(error):
                raise AgentUnusableError(agent.name, _unreachable(agent.url)) from error
            cause = error if error.__cause__ is None else error.__cause__
            raise AgentUnusableError(
                agent.name, f"could not be fetched from {agent.url}: {cause}"
            ) from error
        skills = tuple(skill.id for skill in card.skills)
        if SKILL_ID not in skills:
            raise AgentUnusableError(
                agent.name, f"does not advertise skill '{SKILL_ID}' (has {skills})"
            )
        interface_url = _jsonrpc_url(card)
        if interface_url is None:
            raise AgentUnusableError(agent.name, "advertises no JSON-RPC interface")
        secret_header = _credential_header(agent.name, card)
        if not agent.token:
            raise AgentUnusableError(agent.name, "requires a caller secret but none is registered")
        if self._cards.get(agent.name) != card:
            # The SDK client is bound to the card's interface URL; a changed card needs a new one.
            self._clients.pop(agent.name, None)
        self._cards[agent.name] = card
        self._secret_headers[agent.name] = secret_header
        return AgentInfo(
            name=agent.name,
            url=interface_url,
            streaming=card.capabilities.streaming,
            skills=skills,
        )

    async def fetch_month(
        self, agent: AgentConfig, month: str, resume: TaskRef | None, user_token: str
    ) -> AsyncIterator[AgentEvent]:
        client = await self._client_for(agent)
        credentials = ClientCallContext(
            service_parameters={
                "Authorization": f"Bearer {user_token}",
                self._secret_headers[agent.name]: agent.token,
            }
        )
        stream = client.send_message(
            SendMessageRequest(message=_request_message(month, resume)), context=credentials
        )
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
            log.warning("fetch failed", agent=agent.name, error=str(error))
            if _refused_secret(error):
                yield TaskFailed(agent.name, "refused this agent's secret; check its registration")
            elif _connection_lost(error):
                called = _jsonrpc_url(self._cards[agent.name])
                assert called is not None, "discover admitted this card"
                yield TaskFailed(agent.name, _unreachable_call(agent, called))
            else:
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
        self._secret_headers.clear()

    def _http_for(self, agent: AgentConfig) -> httpx.AsyncClient:
        if agent.name not in self._http:
            self._http[agent.name] = self._http_factory()
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


def _credential_header(agent: str, card: AgentCard) -> str:
    """The header name of the card's API key scheme, once the card is known to ask for the
    person's OpenID Connect token and the caller's API key together in one requirement."""
    oidc = {
        name for name, scheme in card.security_schemes.items()
        if scheme.HasField("open_id_connect_security_scheme")
    }
    api_keys = {
        name: scheme.api_key_security_scheme.name
        for name, scheme in card.security_schemes.items()
        if scheme.HasField("api_key_security_scheme")
        and scheme.api_key_security_scheme.location.lower() == "header"
    }
    if not oidc:
        raise AgentUnusableError(agent, "declares no OpenID Connect scheme for the person")
    if not api_keys:
        raise AgentUnusableError(agent, "declares no header API key scheme for the caller")
    for requirement in card.security_requirements:
        required = set(requirement.schemes)
        if required & oidc and required & set(api_keys):
            [api_key] = required & set(api_keys)
            return api_keys[api_key]
    raise AgentUnusableError(
        agent, "does not require the person's token and the caller secret together"
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
    raise AgentUnusableError(agent, "sent a stream response with no task, update or message")


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
    if state in _PAUSED_STATES:
        asked = _PAUSED_STATES[state]
        if text is None:
            raise AgentUnusableError(agent, f"{asked} without any text for the human")
        reason, month, page = _input_request(agent, parts, asked)
        if state == TaskState.TASK_STATE_AUTH_REQUIRED and reason != SIGN_IN_REQUIRED:
            raise AgentUnusableError(
                agent, f"{asked} with reason {reason!r} instead of {SIGN_IN_REQUIRED}"
            )
        events.append(InputRequired(agent, ref, text, reason, month, page))
    elif state == TaskState.TASK_STATE_COMPLETED:
        events.append(TaskCompleted(agent, ref))
    elif state in _FAILED_STATES:
        events.append(TaskFailed(agent, text if text is not None else TaskState.Name(state)))
    return events


def _input_request(
    agent: str, parts: Sequence[Part], asked: str
) -> tuple[str, str, str | None]:
    """The reason, month and optional page of a paused status, all in one data part.

    The page must be a path on the agent's own origin, so a link built from it cannot lead
    anywhere else.
    """
    data = get_data_parts(parts)
    if len(data) != 1:
        raise AgentUnusableError(agent, f"{asked} with {len(data)} data parts instead of one")
    missing = [key for key in ("reason", "month") if key not in data[0]]
    if missing:
        raise AgentUnusableError(
            agent, f"{asked} without {' and '.join(missing)} in its data part"
        )
    page = data[0].get("page")
    if page is not None and not (
        isinstance(page, str) and page.startswith("/") and not page.startswith("//")
    ):
        raise AgentUnusableError(agent, f"{asked} with page {page!r}, not a path")
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
