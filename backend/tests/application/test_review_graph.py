from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from hfm.application.event_sink import ReviewEventSink
from hfm.application.questions import build_questions
from hfm.application.review_graph import GraphDeps, build_review_graph, checkpoint_serde
from hfm.application.user_token import current_user_token, with_user_token
from hfm.domain.errors import AgentUnusableError, InvalidAnswersError, ReviewError
from hfm.domain.events import (
    AGENT_DISCOVERED,
    AGENT_STATUS,
    REVIEW_QUESTION,
    REVIEW_REPORT,
    REVIEW_TOTALS,
    TRANSACTIONS_BATCH,
)
from hfm.domain.merchants import merchant_key
from hfm.domain.models import (
    AgentConfig,
    Budget,
    CategoryTotal,
    Confidence,
    Installment,
    TaskRef,
    Transaction,
)
from hfm.ports import (
    SIGN_IN_REQUIRED,
    AgentEvent,
    AgentInfo,
    InputRequired,
    StatusEvent,
    TaskCompleted,
    TaskFailed,
    TransactionsBatch,
)
from tests.builders import make_tx
from tests.fakes import (
    FakeReportWriter,
    InMemoryEventBus,
    InMemoryMerchantMemory,
    InMemoryReviewEventStore,
    ScriptedCardAgentClient,
)

MONTH = "2026-09"
AMEX = AgentConfig("amex", "http://amex.test", "token", "http://localhost:8020")
AMEX_INFO = AgentInfo("amex", "http://amex.test", True, ("monthly-transactions",))
VISA = AgentConfig("visa", "http://visa.test", "token", "http://localhost:8030")
VISA_INFO = AgentInfo("visa", "http://visa.test", True, ("monthly-transactions",))
TASK = TaskRef("amex", "t1", "c1")
VISA_TASK = TaskRef("visa", "t7", "c7")
BUDGET = Budget("ILS", {"groceries": Decimal(500), "dining": Decimal(100)})
CONFIG: Any = {"configurable": {"thread_id": "r1"}}
USER = "1001"
USER_TOKEN = "eyJ-user-token-never-checkpointed"

GROCERIES = make_tx(id="1", raw_merchant="שופרסל דיל", merchant="Shufersal", category="groceries")
DINING = make_tx(id="2", raw_merchant="קפה גרג", merchant="Cafe Greg", category="dining")
UNKNOWN = make_tx(id="3")
UNKNOWN_KEY = merchant_key(UNKNOWN.raw_merchant)

WORKING = StatusEvent("amex", "TASK_STATE_WORKING", "Reading statements")
COMPLETED = TaskCompleted("amex", TASK)
NEEDS_CODE = InputRequired("amex", TASK, "Enter the SMS code", "auth", MONTH, None)
STATEMENT_MISSING = InputRequired(
    "amex", TASK, "No statement covers 2026-09", "statement-missing", MONTH, "/statements.html"
)


def batch(*transactions: Transaction) -> TransactionsBatch:
    return TransactionsBatch(transactions[0].agent, MONTH, transactions)


@dataclass
class Harness:
    graph: Any
    saver: InMemorySaver
    client: ScriptedCardAgentClient
    memory: InMemoryMerchantMemory
    store: InMemoryReviewEventStore
    writer: FakeReportWriter

    async def event_types(self) -> list[str]:
        return [event.type for _, event in await self.store.list("r1")]

    async def event_data(self, event_type: str) -> list[dict[str, Any]]:
        return [e.data for _, e in await self.store.list("r1") if e.type == event_type]


def deps(
    *scripts: list[AgentEvent],
    client: ScriptedCardAgentClient | None = None,
    agents: tuple[AgentConfig, ...] = (AMEX,),
    saver: InMemorySaver | None = None,
) -> Harness:
    client = client or ScriptedCardAgentClient({"amex": AMEX_INFO}, {"amex": list(scripts)})
    memory, store = InMemoryMerchantMemory(), InMemoryReviewEventStore()
    writer = FakeReportWriter()
    sink = ReviewEventSink(store, InMemoryEventBus())
    graph_deps = GraphDeps(client, memory, BUDGET, writer, sink, {a.name: a for a in agents})
    saver = saver or InMemorySaver(serde=checkpoint_serde())
    return Harness(build_review_graph(graph_deps, saver), saver, client, memory, store, writer)


async def run(h: Harness, payload: Any = None) -> dict[str, Any]:
    """Invokes the graph the way the runner does: with the person's token in the run's context."""
    start = {"month": MONTH, "user_id": USER}
    with with_user_token(USER_TOKEN):
        result: dict[str, Any] = await h.graph.ainvoke(
            start if payload is None else payload, CONFIG
        )
    return result


def answer(answers: dict[str, str]) -> Command[Any]:
    return Command(resume={"answers": answers})


def spent(result: dict[str, Any]) -> dict[str, Decimal]:
    return {t.category: t.spent for t in result["totals"]}


@pytest.fixture(autouse=True)
def no_blocked_checkpoint_types(caplog: pytest.LogCaptureFixture) -> Iterator[None]:
    yield
    serde_warnings = [
        r for r in caplog.records
        if r.name.startswith("langgraph.checkpoint") and r.levelno >= logging.WARNING
    ]
    assert serde_warnings == []


async def test_happy_path_streams_totals_and_report() -> None:
    h = deps([WORKING, batch(GROCERIES, DINING), COMPLETED])

    result = await run(h)

    assert "__interrupt__" not in result
    assert result["transactions"] == [GROCERIES, DINING]
    assert spent(result) == {"groceries": GROCERIES.amount, "dining": DINING.amount}
    assert result["report"] == "canned report"
    assert await h.event_types() == [
        AGENT_DISCOVERED, AGENT_STATUS, TRANSACTIONS_BATCH, REVIEW_TOTALS, REVIEW_REPORT,
    ]


async def test_totals_carry_the_standing_order_spend() -> None:
    gym = make_tx(id="9", raw_merchant="וים קלאבס", category="health", standing_order=True,
                  amount=Decimal("308.00"))
    h = deps([batch(GROCERIES, gym), COMPLETED])

    await run(h)

    assert (await h.event_data(REVIEW_TOTALS))[-1]["standingOrders"] == "308.00"


async def test_uncategorized_merchant_interrupts_then_resumes_and_remembers() -> None:
    h = deps([batch(GROCERIES, UNKNOWN), COMPLETED])

    paused = await run(h)
    [pending] = paused["__interrupt__"]
    assert [q["kind"] for q in pending.value["questions"]] == ["categorize"]
    assert pending.value["questions"][0]["id"] == f"cat:{UNKNOWN_KEY}"

    result = await run(h, answer({f"cat:{UNKNOWN_KEY}": "dining"}))

    assert result["report"] == "canned report"
    assert await h.memory.lookup(USER, [UNKNOWN_KEY]) == {UNKNOWN_KEY: "dining"}
    assert await h.memory.lookup("1002", [UNKNOWN_KEY]) == {}
    assert spent(result)["dining"] == UNKNOWN.amount
    assert (await h.event_types()).count(REVIEW_QUESTION) == 1
    assert (await h.event_data(REVIEW_TOTALS))[-1]["chosen"] == {"amex": [UNKNOWN.id]}


async def test_memory_prevents_the_question_second_time() -> None:
    h = deps([batch(UNKNOWN), COMPLETED])
    await h.memory.remember(USER, UNKNOWN_KEY, "health")

    result = await run(h)

    assert "__interrupt__" not in result
    assert spent(result)["health"] == UNKNOWN.amount


async def test_unanswered_merchant_stays_uncategorized_and_is_not_asked_again() -> None:
    second = make_tx(id="4", raw_merchant=UNKNOWN.raw_merchant)
    h = deps([batch(UNKNOWN), NEEDS_CODE], [batch(second), COMPLETED])

    paused = await run(h)
    [question] = paused["__interrupt__"][0].value["questions"][:1]
    assert [t["id"] for t in question["transactions"]] == [UNKNOWN.id]

    result = await run(h, answer({"remote:amex": "continue"}))

    assert "__interrupt__" not in result
    assert spent(result)["uncategorized"] == UNKNOWN.amount + second.amount
    assert await h.memory.lookup(USER, [UNKNOWN_KEY]) == {}
    assert (await h.event_types()).count(REVIEW_QUESTION) == 1


async def test_low_confidence_guess_is_asked_and_kept_when_left_unanswered() -> None:
    guess = make_tx(id="5", raw_merchant="Amazon 1", category="shopping",
                    confidence=Confidence.LOW)
    sure = make_tx(id="6", raw_merchant="Paz", category="transport",
                   confidence=Confidence.MEDIUM)
    h = deps([batch(guess, sure), COMPLETED])

    paused = await run(h)
    [question] = paused["__interrupt__"][0].value["questions"]
    assert question["id"] == f"cat:{merchant_key(guess.raw_merchant)}"

    result = await run(h, answer({}))

    assert spent(result)["shopping"] == guess.amount
    assert await h.memory.lookup(USER, [merchant_key(guess.raw_merchant)]) == {}


async def test_remembered_category_outranks_the_agent_category() -> None:
    h = deps([batch(GROCERIES), COMPLETED])
    await h.memory.remember(USER, merchant_key(GROCERIES.raw_merchant), "health")

    result = await run(h)

    assert spent(result) == {"health": GROCERIES.amount, "groceries": 0, "dining": 0}


async def test_remote_input_required_continue_refetches_same_task() -> None:
    h = deps([batch(GROCERIES), NEEDS_CODE], [batch(DINING), COMPLETED])

    paused = await run(h)
    assert [q["kind"] for q in paused["__interrupt__"][0].value["questions"]] == ["remote-input"]

    result = await run(h, answer({"remote:amex": "continue"}))

    assert h.client.calls == [("amex", MONTH, None), ("amex", MONTH, TASK)]
    assert result["transactions"] == [GROCERIES, DINING]
    assert result["pending_remote"] == {}
    assert result["report"] == "canned report"


async def test_statement_page_links_on_the_agent_browser_address_and_continue_resumes() -> None:
    h = deps([STATEMENT_MISSING], [batch(GROCERIES), COMPLETED])

    paused = await run(h)
    [question] = paused["__interrupt__"][0].value["questions"]
    assert question["link"] == "http://localhost:8020/statements.html"
    assert question["actions"] == ["continue"]

    result = await run(h, answer({"remote:amex": "continue"}))

    assert h.client.calls == [("amex", MONTH, None), ("amex", MONTH, TASK)]
    assert result["transactions"] == [GROCERIES]


async def test_remote_input_required_skip_reports_with_partial_data() -> None:
    h = deps([batch(GROCERIES), NEEDS_CODE])

    await run(h)
    result = await run(h, answer({"remote:amex": "skip"}))

    assert result["report"] == "canned report"
    assert result["skipped"] == {"amex": True}
    assert result["transactions"] == [GROCERIES]
    assert len(h.client.calls) == 1
    assert "skipped and their spend is missing: amex;" in h.writer.prompts[-1]
    assert (await h.event_data(REVIEW_TOTALS))[-1]["skipped"] == ["amex"]


async def test_two_agents_continue_refetches_only_the_waiting_one() -> None:
    visa_rows = (make_tx(id="v1", agent="visa", category="groceries"),
                 make_tx(id="v2", agent="visa", category="dining"))
    client = ScriptedCardAgentClient(
        {"amex": AMEX_INFO, "visa": VISA_INFO},
        {
            "amex": [[NEEDS_CODE], [batch(DINING), COMPLETED]],
            "visa": [[batch(*visa_rows), TaskCompleted("visa", VISA_TASK)]],
        },
    )
    h = deps(client=client, agents=(AMEX, VISA))

    await run(h)
    result = await run(h, answer({"remote:amex": "continue"}))

    first_pass, refetch = h.client.calls[:2], h.client.calls[2:]
    assert set(first_pass) == {("amex", MONTH, None), ("visa", MONTH, None)}
    assert refetch == [("amex", MONTH, TASK)]
    assert set(result["transactions"]) == {DINING, *visa_rows}
    assert len(result["transactions"]) == 3
    assert result["pending_remote"] == {}
    assert result["tasks"] == {"amex": TASK, "visa": VISA_TASK}
    assert result["report"] == "canned report"


async def test_review_fails_without_card_agents() -> None:
    h = deps(agents=())

    with pytest.raises(ReviewError, match="no card agents are connected"):
        await run(h)


async def test_one_agent_failing_its_task_fails_the_review_naming_it() -> None:
    client = ScriptedCardAgentClient(
        {"amex": AMEX_INFO, "visa": VISA_INFO},
        {
            "amex": [[WORKING, TaskFailed("amex", "statement file is unreadable")]],
            "visa": [[batch(make_tx(id="v1", agent="visa")), TaskCompleted("visa", VISA_TASK)]],
        },
    )
    h = deps(client=client, agents=(AMEX, VISA))

    with pytest.raises(ReviewError, match="^amex statement file is unreadable"):
        await run(h)


async def test_a_stream_without_a_terminal_event_fails_the_review() -> None:
    h = deps([WORKING, batch(GROCERIES)])

    with pytest.raises(
        ReviewError, match="^amex: stream ended without completing or asking for input"
    ):
        await run(h)


async def test_transactions_resent_on_continue_are_counted_once() -> None:
    h = deps([batch(GROCERIES), NEEDS_CODE], [batch(GROCERIES, DINING), COMPLETED])

    await run(h)
    result = await run(h, answer({"remote:amex": "continue"}))

    assert result["transactions"] == [GROCERIES, DINING]
    assert spent(result)["groceries"] == GROCERIES.amount


async def test_graph_fails_review_when_agent_unusable() -> None:
    class UnusableClient(ScriptedCardAgentClient):
        async def discover(self, agent: AgentConfig) -> AgentInfo:
            raise AgentUnusableError(agent.name, "streaming not supported")

    h = deps(client=UnusableClient({}, {}))

    with pytest.raises(AgentUnusableError):
        await run(h)


def stored_bytes(saver: InMemorySaver) -> list[bytes]:
    """Every serialized blob the saver holds: checkpoints, their metadata and pending writes."""
    found: list[bytes] = []

    def walk(value: Any) -> None:
        if isinstance(value, bytes):
            found.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list | tuple):
            for item in value:
                walk(item)

    walk(saver.storage)
    walk(saver.writes)
    walk(saver.blobs)
    return found


async def test_no_checkpoint_or_pending_write_holds_an_agent_or_user_token() -> None:
    token = "tok-3f9c1e-never-checkpointed"
    agent = AgentConfig("amex", "http://amex.test", token, "http://localhost:8020")
    h = deps([NEEDS_CODE], [batch(GROCERIES), COMPLETED], agents=(agent,))

    await run(h)
    await run(h, answer({"remote:amex": "continue"}))

    assert h.client.tokens == [USER_TOKEN, USER_TOKEN]
    blobs = stored_bytes(h.saver)
    assert any(GROCERIES.raw_merchant.encode() in blob for blob in blobs)
    assert any(USER.encode() in blob for blob in blobs)
    assert not [blob for blob in blobs if token.encode() in blob]
    assert not [blob for blob in blobs if USER_TOKEN.encode() in blob]


async def test_a_fetch_without_a_signed_in_person_is_a_bug_not_a_review_failure() -> None:
    h = deps([batch(GROCERIES), COMPLETED])
    with pytest.raises(LookupError):
        await h.graph.ainvoke({"month": MONTH, "user_id": USER}, CONFIG)
    with pytest.raises(LookupError):
        current_user_token()


async def test_sign_in_required_pauses_with_continue_only_and_the_continue_refetches() -> None:
    sign_in = InputRequired(
        "amex", TASK, "amex-agent could not verify who you are (expired).", SIGN_IN_REQUIRED,
        MONTH, None,
    )
    h = deps([sign_in], [batch(GROCERIES), COMPLETED])

    paused = await run(h)
    [question] = paused["__interrupt__"][0].value["questions"]
    assert question["reason"] == SIGN_IN_REQUIRED
    assert question["actions"] == ["continue"]
    assert question["link"] is None

    result = await run(h, answer({"remote:amex": "continue"}))

    assert h.client.calls == [("amex", MONTH, None), ("amex", MONTH, TASK)]
    assert result["transactions"] == [GROCERIES]


async def test_resuming_after_the_agent_left_the_config_fails_naming_it() -> None:
    h = deps([NEEDS_CODE], [batch(GROCERIES), COMPLETED])
    await run(h)
    reconfigured = deps(client=h.client, agents=(), saver=h.saver)

    with pytest.raises(ReviewError, match="^amex is no longer configured"):
        await run(reconfigured, answer({"remote:amex": "continue"}))


async def test_a_missing_remote_answer_is_rejected_on_resume() -> None:
    h = deps([batch(UNKNOWN), NEEDS_CODE])
    await run(h)

    with pytest.raises(InvalidAnswersError):
        await run(h, answer({f"cat:{UNKNOWN_KEY}": "dining"}))


def shape(value: Any) -> Any:
    """Msgpack restores tuples as lists; compare sequences alike but keep every value's type."""
    if is_dataclass(value):
        return type(value), {f.name: shape(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, list | tuple):
        return [shape(v) for v in value]
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    return value


def test_checkpoint_serde_round_trips_review_state() -> None:
    serde = checkpoint_serde()
    installment_tx = make_tx(installment=Installment(2, 6))
    state = {
        "user_id": USER,
        "agents": ["amex"],
        "infos": {"amex": AMEX_INFO},
        "tasks": {"amex": TASK},
        "transactions": [installment_tx],
        "pending_remote": {"amex": NEEDS_CODE, "visa": STATEMENT_MISSING},
        "left_unanswered": {UNKNOWN_KEY: True},
        "totals": [CategoryTotal("dining", Decimal("1.50"), None)],
        "questions": build_questions(
            {UNKNOWN_KEY: (UNKNOWN, installment_tx)},
            {"amex": NEEDS_CODE, "visa": STATEMENT_MISSING},
            {"amex": AMEX, "visa": VISA},
        ),
    }

    assert shape(serde.loads_typed(serde.dumps_typed(state))) == shape(state)


async def test_a_completed_review_recategorizes_a_merchant_and_rewrites_the_report() -> None:
    h = deps([batch(GROCERIES, DINING), COMPLETED])
    await run(h)
    dining_key = merchant_key(DINING.raw_merchant)

    result = await run(h, {"recategorize": {dining_key: "groceries"}})

    assert spent(result) == {"groceries": GROCERIES.amount + DINING.amount, "dining": 0}
    assert result["recategorize"] == {}
    assert await h.memory.lookup(USER, [dining_key]) == {dining_key: "groceries"}
    assert len(h.client.calls) == 1
    assert (await h.event_types())[-2:] == [REVIEW_TOTALS, REVIEW_REPORT]
