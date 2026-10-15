from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest
from a2a.helpers import get_data_parts, new_data_part, new_text_part
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Artifact,
    HTTPAuthSecurityScheme,
    Message,
    Part,
    Role,
    SecurityScheme,
    SendMessageRequest,
    StreamResponse,
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
    AgentEvent,
    InputRequired,
    StatusEvent,
    TaskCompleted,
    TaskFailed,
    TransactionsBatch,
)
from tests.builders import make_tx

AGENT = AgentConfig(
    name="amex", url="http://agent", token="secret", browser_url="http://localhost:8020"
)
TASK_ID = "task-1"
CONTEXT_ID = "ctx-1"

ROW: dict[str, Any] = {
    "id": "201939841",
    "transactionDate": "2026-09-05",
    "chargeDate": "2026-10-02",
    "merchant": "Super-Pharm",
    "rawMerchant": "סופר פארם בעמ 123",
    "amount": 86.9,
    "originalAmount": None,
    "originalCurrency": None,
    "standingOrder": False,
    "abroad": False,
    "installment": None,
    "category": "uncategorized",
    "confidence": "low",
}


def make_card(
    *,
    skills: Sequence[str] = (SKILL_ID,),
    bearer: bool = True,
    binding: str = "JSONRPC",
    url: str = "http://agent/a2a",
) -> AgentCard:
    http_auth = HTTPAuthSecurityScheme(scheme="bearer")
    schemes = {"bearer": SecurityScheme(http_auth_security_scheme=http_auth)} if bearer else {}
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
    )


def serving(card: AgentCard) -> Callable[[str], httpx.AsyncClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/.well-known/agent-card.json"
        return httpx.Response(200, json=MessageToDict(card))

    return lambda token: httpx.AsyncClient(transport=httpx.MockTransport(handler))


class FakeClient:
    """Replays hand-built stream chunks and records every request sent."""

    def __init__(self, chunks: Sequence[StreamResponse], error: Exception | None = None) -> None:
        self.chunks = chunks
        self.error = error
        self.requests: list[SendMessageRequest] = []

    async def send_message(self, request: SendMessageRequest) -> AsyncIterator[StreamResponse]:
        self.requests.append(request)
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
    data = {"month": month, "currency": "ILS", "transactions": rows}
    return Artifact(artifact_id="a", parts=[new_data_part(data)])


def artifact_chunk(month: str, rows: list[dict[str, Any]]) -> StreamResponse:
    return StreamResponse(
        artifact_update=TaskArtifactUpdateEvent(
            task_id=TASK_ID, context_id=CONTEXT_ID, artifact=transactions_artifact(month, rows)
        )
    )


QUESTION = "No statement for 2026-11 yet; upload it and continue."
STATEMENT_MISSING_DATA = {"reason": "statement-missing", "month": "2026-11"}
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

    events = await collect(adapter.fetch_month(AGENT, "2026-10", None))
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

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", None))

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

    events = await collect(
        adapter_for(FakeClient([StreamResponse(task=snapshot)])).fetch_month(AGENT, "2026-11", REF)
    )

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

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", None))

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
        await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", None))

    assert str(refused.value) == f"agent 'amex' is unusable: asked for input {problem}"


async def test_fetch_month_rejects_a_stream_response_with_no_payload() -> None:
    fake = FakeClient([StreamResponse()])

    with pytest.raises(AgentUnusableError, match="carries no task, update or message"):
        await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", None))


async def test_fetch_month_completed_task_snapshot_yields_artifacts_then_completion() -> None:
    snapshot = Task(
        id=TASK_ID,
        context_id=CONTEXT_ID,
        status=status_with(TaskState.TASK_STATE_COMPLETED),
        artifacts=[transactions_artifact("2026-10", [ROW])],
    )

    events = await collect(
        adapter_for(FakeClient([StreamResponse(task=snapshot)])).fetch_month(AGENT, "2026-10", REF)
    )

    assert events == [
        TransactionsBatch("amex", "2026-10", (make_tx(),)),
        StatusEvent("amex", "TASK_STATE_COMPLETED", None),
        TaskCompleted("amex", REF),
    ]


async def test_fetch_month_discovers_first_and_rejects_card_without_skill() -> None:
    adapter = adapter_for(FakeClient([]), make_card(skills=("other",)))

    with pytest.raises(AgentUnusableError, match=SKILL_ID):
        await anext(adapter.fetch_month(AGENT, "2026-10", None))


async def test_fetch_month_resume_sets_task_and_context_ids() -> None:
    fake = FakeClient([status_chunk(TaskState.TASK_STATE_COMPLETED)])

    await collect(adapter_for(fake).fetch_month(AGENT, "2026-11", REF))

    message = fake.requests[0].message
    assert (message.task_id, message.context_id) == (TASK_ID, CONTEXT_ID)
    assert get_data_parts(message.parts) == [{"action": "continue"}]


async def test_fetch_month_reports_failed_state_with_agent_text() -> None:
    fake = FakeClient(
        [status_chunk(TaskState.TASK_STATE_FAILED, [new_text_part("statement unreadable")])]
    )

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-10", None))

    assert events[-1] == TaskFailed("amex", "statement unreadable")


async def test_fetch_month_surfaces_sdk_error_as_task_failed() -> None:
    fake = FakeClient([task_chunk(TaskState.TASK_STATE_SUBMITTED)], error=InternalError("boom"))

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-10", None))

    assert events == [
        StatusEvent("amex", "TASK_STATE_SUBMITTED", None),
        TaskFailed("amex", "boom"),
    ]


async def test_fetch_month_fails_when_stream_ends_without_final_state() -> None:
    fake = FakeClient([status_chunk(TaskState.TASK_STATE_WORKING)])

    events = await collect(adapter_for(fake).fetch_month(AGENT, "2026-10", None))

    assert isinstance(events[-1], TaskFailed)
    assert "TASK_STATE_WORKING" in events[-1].message


async def test_discover_returns_card_capabilities() -> None:
    adapter = adapter_for(FakeClient([]), make_card())

    info = await adapter.discover(AGENT)

    assert (info.name, info.url, info.streaming) == ("amex", "http://agent/a2a", True)
    assert info.skills == (SKILL_ID,)


async def test_default_http_sends_the_token_and_waits_long_between_stream_events() -> None:
    async with default_http("tok") as http:
        assert http.headers["Authorization"] == "Bearer tok"
        assert http.timeout == httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)


async def test_a_changed_card_on_rediscovery_gets_a_new_sdk_client() -> None:
    served = [make_card(), make_card(), make_card(url="http://moved/a2a")]

    def card(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=MessageToDict(served.pop(0)))

    built: list[str] = []

    def client_factory(card: AgentCard, http: httpx.AsyncClient) -> FakeClient:
        built.append(card.supported_interfaces[0].url)
        return FakeClient([task_chunk(TaskState.TASK_STATE_COMPLETED)])

    adapter = A2ACardAgentClient(
        http_factory=lambda token: httpx.AsyncClient(transport=httpx.MockTransport(card)),
        client_factory=client_factory,
    )
    for _ in served[:]:
        await adapter.discover(AGENT)
        await collect(adapter.fetch_month(AGENT, "2026-10", None))

    assert built == ["http://agent/a2a", "http://moved/a2a"]


async def test_discover_rejects_card_without_skill() -> None:
    adapter = adapter_for(FakeClient([]), make_card(skills=("other",)))

    with pytest.raises(AgentUnusableError, match=SKILL_ID):
        await adapter.discover(AGENT)


async def test_discover_rejects_card_without_jsonrpc_interface() -> None:
    adapter = adapter_for(FakeClient([]), make_card(binding="GRPC"))

    with pytest.raises(AgentUnusableError, match="JSON-RPC"):
        await adapter.discover(AGENT)


async def test_discover_rejects_card_without_bearer_scheme() -> None:
    adapter = adapter_for(FakeClient([]), make_card(bearer=False))

    with pytest.raises(AgentUnusableError, match="no HTTP bearer security scheme"):
        await adapter.discover(AGENT)


async def test_discover_rejects_bearer_card_without_token() -> None:
    adapter = adapter_for(FakeClient([]), make_card())

    with pytest.raises(AgentUnusableError, match="token"):
        await adapter.discover(replace(AGENT, token=""))


async def test_discover_rejects_unreachable_card() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    adapter = A2ACardAgentClient(
        http_factory=lambda token: httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    )

    with pytest.raises(AgentUnusableError, match="401"):
        await adapter.discover(AGENT)


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
