from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest
from a2a.client import A2AClientError, ClientCallContext
from a2a.helpers import get_data_parts, new_data_part, new_text_part
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    APIKeySecurityScheme,
    Artifact,
    Message,
    OpenIdConnectSecurityScheme,
    Part,
    Role,
    SecurityRequirement,
    SecurityScheme,
    SendMessageRequest,
    StreamResponse,
    StringList,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils.errors import InternalError
from google.protobuf.json_format import MessageToDict

from hfm.adapters.a2a_client import (
    SKILL_ID,
    A2ACardAgentClient,
    default_http,
    parse_transaction,
)
from hfm.domain.errors import AgentUnusableError
from hfm.domain.models import AgentConfig, Confidence, Installment, TaskRef
from hfm.ports.card_agent import (
    SIGN_IN_REQUIRED,
    AgentEvent,
    InputRequired,
    StatusEvent,
    TaskCompleted,
    TaskFailed,
    TransactionsBatch,
)
from tests.builders import ROW, STATEMENT_MISSING_DATA, make_tx, transactions_batch

AGENT = AgentConfig(
    name="amex", url="http://agent", token="secret", browser_url="http://localhost:8020"
)
TASK_ID = "task-1"
CONTEXT_ID = "ctx-1"
USER_TOKEN = "eyJ-the-persons-id-token"
SECRET_HEADER = "X-Caller-Secret"
GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"


def make_card(
    *,
    skills: Sequence[str] = (SKILL_ID,),
    oidc: bool = True,
    api_key: bool = True,
    api_key_location: str = "header",
    secret_header: str = SECRET_HEADER,
    required_together: bool = True,
    binding: str = "JSONRPC",
    url: str = "http://agent/a2a",
) -> AgentCard:
    """A card asking, by default, for the person's Google token and the caller secret together,
    the way amex-agent's does."""
    schemes: dict[str, SecurityScheme] = {}
    if oidc:
        schemes["google"] = SecurityScheme(
            open_id_connect_security_scheme=OpenIdConnectSecurityScheme(
                open_id_connect_url=GOOGLE_DISCOVERY
            )
        )
    if api_key:
        schemes["caller"] = SecurityScheme(
            api_key_security_scheme=APIKeySecurityScheme(
                location=api_key_location, name=secret_header
            )
        )
    requirements = (
        [SecurityRequirement(schemes={name: StringList() for name in schemes})]
        if required_together
        else [SecurityRequirement(schemes={name: StringList()}) for name in schemes]
    )
    return AgentCard(
        name="amex",
        version="1",
        description="card agent",
        supported_interfaces=[
            AgentInterface(url=url, protocol_binding=binding, protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(streaming=True),
        skills=[AgentSkill(id=s, name=s, description=s) for s in skills],
        security_schemes=schemes,
        security_requirements=requirements,
    )


def serving(card: AgentCard) -> Callable[[], httpx.AsyncClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/.well-known/agent-card.json"
        return httpx.Response(200, json=MessageToDict(card))

    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


class FakeClient:
    """Replays hand-built stream chunks and records every request sent with its call context."""

    def __init__(self, chunks: Sequence[StreamResponse], error: Exception | None = None) -> None:
        self.chunks = chunks
        self.error = error
        self.requests: list[SendMessageRequest] = []
        self.contexts: list[ClientCallContext | None] = []

    async def send_message(
        self, request: SendMessageRequest, *, context: ClientCallContext | None = None
    ) -> AsyncIterator[StreamResponse]:
        self.requests.append(request)
        self.contexts.append(context)
        for chunk in self.chunks:
            yield chunk
        if self.error is not None:
            raise self.error


def adapter_for(fake: FakeClient, card: AgentCard | None = None) -> A2ACardAgentClient:
    return A2ACardAgentClient(
        http_factory=serving(card if card is not None else make_card()),
        client_factory=lambda card, http: fake,
    )


def task_chunk(state: int) -> StreamResponse:
    return StreamResponse(
        task=Task(id=TASK_ID, context_id=CONTEXT_ID, status=TaskStatus(state=state))
    )


def status_with(state: int, parts: Sequence[Part] = ()) -> TaskStatus:
    message = Message(role=Role.ROLE_AGENT, message_id="m", parts=list(parts))
    return TaskStatus(state=state, message=message)


def status_chunk(state: int, parts: Sequence[Part] = ()) -> StreamResponse:
    return StreamResponse(
        status_update=TaskStatusUpdateEvent(
            task_id=TASK_ID, context_id=CONTEXT_ID, status=status_with(state, parts)
        )
    )


def transactions_artifact(month: str, rows: list[dict[str, Any]]) -> Artifact:
    return Artifact(artifact_id="a", parts=[new_data_part(transactions_batch(month, rows))])


def artifact_chunk(month: str, rows: list[dict[str, Any]]) -> StreamResponse:
    return StreamResponse(
        artifact_update=TaskArtifactUpdateEvent(
            task_id=TASK_ID, context_id=CONTEXT_ID, artifact=transactions_artifact(month, rows)
        )
    )


QUESTION = "No statement for 2026-11 yet; upload it and continue."
STATEMENT_MISSING = [new_text_part(QUESTION), new_data_part(STATEMENT_MISSING_DATA)]
REF = TaskRef(agent="amex", task_id=TASK_ID, context_id=CONTEXT_ID)


async def collect(events: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    return [event async for event in events]


async def test_fetch_month_translates_stream_to_events() -> None:
    fake = FakeClient(
        [
            task_chunk(TaskState.TASK_STATE_SUBMITTED),
            status_chunk(TaskState.TASK_STATE_WORKING, [new_text_part("reading statement")]),
            artifact_chunk("2026-10", [ROW]),
            status_chunk(TaskState.TASK_STATE_COMPLETED),
        ]
    )
    adapter = adapter_for(fake)

    events = await collect(adapter.fetch_month(AGENT, "2026-10", None, USER_TOKEN))
    await adapter.aclose()

    assert events == [
        StatusEvent("amex", "TASK_STATE_SUBMITTED", None),
        StatusEvent("amex", "TASK_STATE_WORKING", "reading statement"),
        TransactionsBatch("amex", "2026-10", (make_tx(),)),
        StatusEvent("amex", "TASK_STATE_COMPLETED", None),
        TaskCompleted("amex", REF),
    ]
    assert get_data_parts(fake.requests[0].message.parts) == [{"month": "2026-10"}]
    assert fake.requests[0].message.role == Role.ROLE_USER


async def test_fetch_month_input_required_carries_task_ref() -> None:
    fake = FakeClient([status_chunk(TaskState.TASK_STATE_INPUT_REQUIRED, STATEMENT_MISSING)])

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", None, USER_TOKEN))

    assert events == [
        StatusEvent("amex", "TASK_STATE_INPUT_REQUIRED", QUESTION),
        InputRequired("amex", REF, QUESTION, "statement-missing", "2026-11", None),
    ]


async def test_fetch_month_input_required_task_snapshot_carries_task_ref() -> None:
    snapshot = Task(
        id=TASK_ID,
        context_id=CONTEXT_ID,
        status=status_with(TaskState.TASK_STATE_INPUT_REQUIRED, STATEMENT_MISSING),
    )

    adapter = adapter_for(FakeClient([StreamResponse(task=snapshot)]))
    events = await collect(adapter.fetch_month(AGENT, "2026-11", REF, USER_TOKEN))

    assert events == [
        StatusEvent("amex", "TASK_STATE_INPUT_REQUIRED", QUESTION),
        InputRequired("amex", REF, QUESTION, "statement-missing", "2026-11", None),
    ]


async def test_fetch_month_input_required_carries_the_agent_page() -> None:
    parts = [
        new_text_part(QUESTION),
        new_data_part({**STATEMENT_MISSING_DATA, "page": "/statements.html"}),
    ]
    fake = FakeClient([status_chunk(TaskState.TASK_STATE_INPUT_REQUIRED, parts)])

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", None, USER_TOKEN))

    assert events[-1] == InputRequired(
        "amex", REF, QUESTION, "statement-missing", "2026-11", "/statements.html"
    )


@pytest.mark.parametrize(
    ("parts", "problem"),
    [
        (
            [new_text_part(QUESTION), new_data_part({"reason": "statement-missing"})],
            "without month in its data part",
        ),
        *(
            (
                [new_text_part(QUESTION), new_data_part({**STATEMENT_MISSING_DATA, "page": page})],
                f"with page {page!r}, not a path",
            )
            for page in ("statements.html", "//evil.test/statements.html", 7.0)
        ),
        ([STATEMENT_MISSING[1]], "without any text for the human"),
        ([new_text_part(QUESTION)], "with 0 data parts instead of one"),
    ],
)
async def test_fetch_month_malformed_input_request_names_the_agent_and_the_problem(
    parts: list[Part], problem: str
) -> None:
    fake = FakeClient([status_chunk(TaskState.TASK_STATE_INPUT_REQUIRED, parts)])

    with pytest.raises(AgentUnusableError) as refused:
        await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", None, USER_TOKEN))

    assert str(refused.value) == f"amex asked for input {problem}"


async def test_fetch_month_rejects_a_stream_response_with_no_payload() -> None:
    fake = FakeClient([StreamResponse()])

    with pytest.raises(AgentUnusableError, match="no task, update or message"):
        await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", None, USER_TOKEN))


async def test_fetch_month_completed_task_snapshot_yields_artifacts_then_completion() -> None:
    snapshot = Task(
        id=TASK_ID,
        context_id=CONTEXT_ID,
        status=status_with(TaskState.TASK_STATE_COMPLETED),
        artifacts=[transactions_artifact("2026-10", [ROW])],
    )

    adapter = adapter_for(FakeClient([StreamResponse(task=snapshot)]))
    events = await collect(adapter.fetch_month(AGENT, "2026-10", REF, USER_TOKEN))

    assert events == [
        TransactionsBatch("amex", "2026-10", (make_tx(),)),
        StatusEvent("amex", "TASK_STATE_COMPLETED", None),
        TaskCompleted("amex", REF),
    ]


async def test_fetch_month_discovers_first_and_rejects_card_without_skill() -> None:
    adapter = adapter_for(FakeClient([]), make_card(skills=("other",)))

    with pytest.raises(AgentUnusableError, match=SKILL_ID):
        await anext(adapter.fetch_month(AGENT, "2026-10", None, USER_TOKEN))


async def test_fetch_month_resume_sets_task_and_context_ids() -> None:
    fake = FakeClient([status_chunk(TaskState.TASK_STATE_COMPLETED)])

    await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", REF, USER_TOKEN))

    message = fake.requests[0].message
    assert (message.task_id, message.context_id) == (TASK_ID, CONTEXT_ID)
    assert get_data_parts(message.parts) == [{"action": "continue"}]


async def test_fetch_month_reports_failed_state_with_agent_text() -> None:
    fake = FakeClient(
        [status_chunk(TaskState.TASK_STATE_FAILED, [new_text_part("statement unreadable")])]
    )

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-10", None, USER_TOKEN))

    assert events[-1] == TaskFailed("amex", "statement unreadable")


async def test_fetch_month_surfaces_sdk_error_as_task_failed() -> None:
    fake = FakeClient([task_chunk(TaskState.TASK_STATE_SUBMITTED)], error=InternalError("boom"))

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-10", None, USER_TOKEN))

    assert events == [
        StatusEvent("amex", "TASK_STATE_SUBMITTED", None),
        TaskFailed("amex", "boom"),
    ]


async def test_fetch_month_fails_when_stream_ends_without_final_state() -> None:
    fake = FakeClient([status_chunk(TaskState.TASK_STATE_WORKING)])

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-10", None, USER_TOKEN))

    assert isinstance(events[-1], TaskFailed)
    assert "TASK_STATE_WORKING" in events[-1].message


async def test_discover_returns_card_capabilities() -> None:
    adapter = adapter_for(FakeClient([]), make_card())

    info = await adapter.discover(AGENT)

    assert (info.name, info.url, info.streaming) == ("amex", "http://agent/a2a", True)
    assert info.skills == (SKILL_ID,)


async def test_default_http_carries_no_credentials_and_waits_long_between_stream_events() -> None:
    async with default_http() as http:
        assert "Authorization" not in http.headers
        assert http.timeout == httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)


async def test_each_call_carries_the_persons_token_and_the_secret_under_the_cards_header(
) -> None:
    fake = FakeClient([status_chunk(TaskState.TASK_STATE_COMPLETED)])
    adapter = adapter_for(fake, make_card(secret_header="X-Partner-Key"))

    await collect(adapter.fetch_month(AGENT, "2026-10", None, "tok-dana"))
    await collect(adapter.fetch_month(AGENT, "2026-10", None, "tok-noam"))

    assert [c.service_parameters for c in fake.contexts if c is not None] == [
        {"Authorization": "Bearer tok-dana", "X-Partner-Key": "secret"},
        {"Authorization": "Bearer tok-noam", "X-Partner-Key": "secret"},
    ]


async def test_fetch_month_auth_required_pauses_with_sign_in_required() -> None:
    text = "amex-agent could not verify who you are (expired). Sign in again and continue."
    parts = [
        new_text_part(text),
        new_data_part({"reason": SIGN_IN_REQUIRED, "month": "2026-11", "user": ""}),
    ]
    fake = FakeClient([status_chunk(TaskState.TASK_STATE_AUTH_REQUIRED, parts)])

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", None, USER_TOKEN))

    assert events == [
        StatusEvent("amex", "TASK_STATE_AUTH_REQUIRED", text),
        InputRequired("amex", REF, text, SIGN_IN_REQUIRED, "2026-11", None),
    ]


async def test_fetch_month_auth_required_with_another_reason_is_unusable() -> None:
    parts = [new_text_part("why"), new_data_part({"reason": "mfa", "month": "2026-11"})]
    fake = FakeClient([status_chunk(TaskState.TASK_STATE_AUTH_REQUIRED, parts)])

    with pytest.raises(AgentUnusableError, match="asked for sign-in with reason 'mfa'"):
        await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", None, USER_TOKEN))


async def test_a_changed_card_on_rediscovery_gets_a_new_sdk_client() -> None:
    served = [make_card(), make_card(), make_card(url="http://moved/a2a")]

    def card(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=MessageToDict(served.pop(0)))

    built: list[str] = []

    def client_factory(card: AgentCard, http: httpx.AsyncClient) -> FakeClient:
        built.append(card.supported_interfaces[0].url)
        return FakeClient([task_chunk(TaskState.TASK_STATE_COMPLETED)])

    adapter = A2ACardAgentClient(
        http_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(card)),
        client_factory=client_factory,
    )
    for _ in served[:]:
        await adapter.discover(AGENT)
        await collect(adapter.fetch_month(AGENT, "2026-10", None, USER_TOKEN))

    assert built == ["http://agent/a2a", "http://moved/a2a"]


async def test_discover_rejects_card_without_skill() -> None:
    adapter = adapter_for(FakeClient([]), make_card(skills=("other",)))

    with pytest.raises(AgentUnusableError, match=SKILL_ID):
        await adapter.discover(AGENT)


async def test_discover_rejects_card_without_jsonrpc_interface() -> None:
    adapter = adapter_for(FakeClient([]), make_card(binding="GRPC"))

    with pytest.raises(AgentUnusableError, match="JSON-RPC"):
        await adapter.discover(AGENT)


@pytest.mark.parametrize(
    ("card", "problem"),
    [
        (make_card(oidc=False), "no OpenID Connect scheme for the person"),
        (make_card(api_key=False), "no header API key scheme for the caller"),
        (make_card(api_key_location="query"), "no header API key scheme for the caller"),
        (make_card(required_together=False), "together"),
    ],
)
async def test_discover_rejects_a_card_that_does_not_ask_for_both_credentials(
    card: AgentCard, problem: str
) -> None:
    adapter = adapter_for(FakeClient([]), card)

    with pytest.raises(AgentUnusableError, match=problem):
        await adapter.discover(AGENT)


async def test_discover_rejects_a_card_asking_for_a_secret_when_none_is_set() -> None:
    adapter = adapter_for(FakeClient([]), make_card())

    with pytest.raises(AgentUnusableError, match="secret"):
        await adapter.discover(replace(AGENT, token=""))


UNREACHABLE = "could not be reached at http://agent; it may not be running"


async def test_discover_names_an_agent_that_refuses_the_connection() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed", request=request)

    adapter = A2ACardAgentClient(
        http_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    )

    with pytest.raises(AgentUnusableError) as refused:
        await adapter.discover(AGENT)

    assert str(refused.value) == f"amex {UNREACHABLE}"


async def test_discover_names_a_card_that_cannot_be_fetched_for_another_reason() -> None:
    def forbid(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    adapter = A2ACardAgentClient(
        http_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(forbid))
    )

    with pytest.raises(AgentUnusableError) as refused:
        await adapter.discover(AGENT)

    assert str(refused.value).startswith("amex could not be fetched from http://agent: ")
    assert "403" in str(refused.value)


def _client_error(cause: Exception) -> A2AClientError:
    error = A2AClientError("HTTP Error 401: ...")
    error.__cause__ = cause
    return error


async def test_fetch_month_names_a_refused_secret() -> None:
    request = httpx.Request("POST", "http://agent/a2a")
    cause = httpx.HTTPStatusError(
        "401", request=request, response=httpx.Response(401, request=request)
    )
    fake = FakeClient([task_chunk(TaskState.TASK_STATE_SUBMITTED)], error=_client_error(cause))

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-10", None, USER_TOKEN))

    assert events[-1] == TaskFailed("amex", "refused this agent's secret; check its registration")


@pytest.mark.parametrize(
    "cause",
    [
        httpx.ConnectError("refused", request=httpx.Request("POST", "http://agent/a2a")),
        httpx.ReadTimeout("slow", request=httpx.Request("POST", "http://agent/a2a")),
    ],
)
async def test_fetch_month_names_a_lost_connection(cause: Exception) -> None:
    fake = FakeClient([task_chunk(TaskState.TASK_STATE_SUBMITTED)], error=_client_error(cause))

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-10", None, USER_TOKEN))

    assert events[-1] == TaskFailed(
        "amex", "could not be reached at http://agent/a2a; it may not be running"
    )


async def test_fetch_month_names_the_advertised_address_when_it_differs_from_the_card() -> None:
    cause = httpx.ConnectError("refused", request=httpx.Request("POST", "http://localhost:8020"))
    fake = FakeClient([], error=_client_error(cause))
    adapter = adapter_for(fake, make_card(url="http://localhost:8020/a2a"))

    events = await collect(adapter.fetch_month(AGENT, "2026-10", None, USER_TOKEN))

    assert events[-1] == TaskFailed(
        "amex",
        "could not be reached at http://localhost:8020/a2a, the address its card advertises "
        "(registered at http://agent); it may not be running",
    )


def test_parse_transaction_maps_wire_fields() -> None:
    row = ROW | {
        "amount": 120.5,
        "originalAmount": 32.1,
        "originalCurrency": "USD",
        "standingOrder": True,
        "abroad": True,
        "installment": {"number": 3.0, "total": 12.0},
        "category": "groceries",
        "confidence": "medium",
    }

    tx = parse_transaction("amex", row)

    assert tx == make_tx(
        amount=Decimal("120.5"),
        original_amount=Decimal("32.1"),
        original_currency="USD",
        standing_order=True,
        abroad=True,
        installment=Installment(number=3, total=12),
        category="groceries",
        confidence=Confidence.MEDIUM,
    )
    assert tx.transaction_date == date(2026, 9, 5)


def test_parse_transaction_rejects_a_numeric_confidence() -> None:
    with pytest.raises(ValueError, match="0.9"):
        parse_transaction("amex", ROW | {"confidence": 0.9})


def test_parse_transaction_rejects_unknown_category() -> None:
    with pytest.raises(ValueError, match="not a budget category"):
        parse_transaction("amex", ROW | {"category": "yachts"})


def test_parse_transaction_rejects_missing_field() -> None:
    row = dict(ROW)
    del row["chargeDate"]

    with pytest.raises(KeyError, match="chargeDate"):
        parse_transaction("amex", row)
