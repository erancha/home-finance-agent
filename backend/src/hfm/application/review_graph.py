"""The monthly review as a resumable LangGraph state machine.

Core building blocks:
- ReviewState: the checkpointed state, with reducers that merge results of parallel fetches;
  it names agents and never holds their configs, and the person's ID token reaches the fetch
  through user_token, so no secret of either kind reaches a checkpoint
- Nodes: discover, fetch_agent (one per agent), reconcile, pose, ask, recategorize, report
- Routing: an initial fan-out to every agent, and after answers a fan-out only to agents told to
  continue, each resuming its own task; a completed review run again with categories goes
  straight to recategorize and report
- checkpoint_serde: the checkpoint serializer that allows exactly the state's value types

The review id is the checkpoint thread id; every node emits its events under it. The state names
the person who owns the review, whose merchant memory the review reads and extends.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send, interrupt

from hfm.application.event_sink import ReviewEventSink
from hfm.application.questions import (
    CATEGORY_OPTIONS,
    build_questions,
    interrupt_payload,
    validate_answers,
)
from hfm.application.reconcile import (
    apply_memory,
    merge_dict,
    merge_transactions,
    standing_orders,
    totals,
    unsure_merchants,
)
from hfm.application.report import report_prompt
from hfm.application.user_token import current_user_token
from hfm.domain.errors import ReviewError
from hfm.domain.events import (
    AGENT_DISCOVERED,
    AGENT_STATUS,
    REVIEW_QUESTION,
    REVIEW_REPORT,
    REVIEW_TOTALS,
    REVIEW_WRITING,
    TRANSACTIONS_BATCH,
    ReviewEvent,
    money_text,
    total_to_dict,
    transaction_to_dict,
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
from hfm.domain.questions import (
    CONTINUE,
    SKIP,
    CategorizeQuestion,
    Question,
    RemoteInputQuestion,
)
from hfm.ports import (
    AgentInfo,
    CardAgentClient,
    InputRequired,
    MerchantMemory,
    ReportWriter,
    StatusEvent,
    TaskCompleted,
    TaskFailed,
    TransactionsBatch,
)

CHECKPOINTED_TYPES: tuple[type, ...] = (
    AgentInfo, CategorizeQuestion, CategoryTotal, Confidence, InputRequired, Installment,
    RemoteInputQuestion, TaskRef, Transaction,
)
"""Every hfm value type that can sit in ReviewState or in a pending fetch request."""


class ReviewState(TypedDict, total=False):
    month: str
    user_id: str
    """The Google account id of the person the review is for, fixed when it starts."""
    agents: list[str]
    """Names of the agents the review fetches from, fixed when it starts."""
    infos: Annotated[dict[str, AgentInfo], merge_dict]
    tasks: Annotated[dict[str, TaskRef], merge_dict]
    """Agent name to the task of its latest fetch; the handle a continued fetch resumes."""
    transactions: Annotated[list[Transaction], merge_transactions]
    pending_remote: Annotated[dict[str, InputRequired], merge_dict]
    skipped: Annotated[dict[str, bool], merge_dict]
    left_unanswered: Annotated[dict[str, bool], merge_dict]
    """Merchant keys the person left unanswered; their rows keep the card agent's category, and
    the review does not ask about them again."""
    resume_agents: list[str]
    """Agents whose task is fetched again after the latest answers; empty ends the review."""
    questions: list[Question]
    """Questions of the current pause; empty when the review has nothing to ask."""
    totals: list[CategoryTotal]
    report: str | None
    recategorize: dict[str, str]
    """Merchant key to category chosen after the review completed; set as the input of a run that
    reapplies them and rewrites the report, and cleared by it."""


class FetchRequest(TypedDict):
    agent: str
    month: str
    resume: TaskRef | None


@dataclass(frozen=True)
class GraphDeps:
    card_client: CardAgentClient
    memory: MerchantMemory
    budget: Budget
    report_writer: ReportWriter
    sink: ReviewEventSink
    agents: Mapping[str, AgentConfig]
    """Agent name to its config; a review's agent names resolve here, never in state."""


def checkpoint_serde() -> JsonPlusSerializer:
    """Serializer that restores the review's value types and blocks every other unknown type."""
    return JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINTED_TYPES)


def _fetch(agent: str, month: str, resume: TaskRef | None) -> Send:
    return Send("fetch_agent", FetchRequest(agent=agent, month=month, resume=resume))


def fan_out(state: ReviewState) -> list[Send]:
    return [_fetch(agent, state["month"], None) for agent in state["agents"]]


def route_start(state: ReviewState) -> str:
    """A completed review invoked again with categories recategorizes instead of refetching."""
    return "recategorize" if state.get("recategorize") else "discover"


def route_after_ask(state: ReviewState) -> list[Send] | str:
    if not state["resume_agents"]:
        return "report"
    return [
        _fetch(name, state["month"], state["tasks"][name]) for name in state["resume_agents"]
    ]


def build_review_graph(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver[Any]
) -> CompiledStateGraph[ReviewState, None, ReviewState, ReviewState]:
    async def emit(event_type: str, data: dict[str, Any]) -> None:
        review_id = get_config()["configurable"]["thread_id"]
        await deps.sink.emit(review_id, ReviewEvent(event_type, data))

    async def publish_totals(
        transactions: list[Transaction], skipped: list[str]
    ) -> list[CategoryTotal]:
        """Publish the totals with what a reader needs to act on them: the skipped agents whose
        spend they lack, each row's category as counted, the rows whose category the person
        chose, and the categories a person may assign."""
        current = totals(transactions, deps.budget)
        categories: dict[str, dict[str, str]] = {}
        chosen: dict[str, list[str]] = {}
        for t in transactions:
            categories.setdefault(t.agent, {})[t.id] = t.category
            if t.chosen:
                chosen.setdefault(t.agent, []).append(t.id)
        await emit(REVIEW_TOTALS, {
            "currency": deps.budget.currency,
            "totals": [total_to_dict(t) for t in current],
            "standingOrders": money_text(standing_orders(transactions)),
            "skipped": skipped,
            "categories": categories,
            "chosen": chosen,
            "options": list(CATEGORY_OPTIONS),
        })
        return current

    def agent_config(name: str) -> AgentConfig:
        """A paused review keeps its agent names while the registry may change under it."""
        if name not in deps.agents:
            raise ReviewError(f"{name} is no longer configured")
        return deps.agents[name]

    async def discover(state: ReviewState) -> dict[str, Any]:
        """An unusable agent fails the whole review."""
        if not deps.agents:
            raise ReviewError("no card agents are connected")
        infos: dict[str, AgentInfo] = {}
        for name, agent in deps.agents.items():
            info = await deps.card_client.discover(agent)
            infos[name] = info
            await emit(AGENT_DISCOVERED, {
                "agent": name, "url": info.url, "streaming": info.streaming,
            })
        return {"agents": list(deps.agents), "infos": infos}

    async def fetch_agent(state: FetchRequest) -> dict[str, Any]:
        """One agent's month fetch; a None pending entry clears an earlier remote question."""
        name = state["agent"]
        fetched: list[Transaction] = []
        task: TaskRef | None = None
        pending: InputRequired | None = None
        stream = deps.card_client.fetch_month(
            agent_config(name), state["month"], state["resume"], current_user_token()
        )
        async for event in stream:
            match event:
                case StatusEvent():
                    await emit(
                        AGENT_STATUS, {"agent": name, "state": event.state, "text": event.text}
                    )
                case TransactionsBatch():
                    fetched.extend(event.transactions)
                    await emit(TRANSACTIONS_BATCH, {
                        "agent": name,
                        "month": event.month,
                        "count": len(event.transactions),
                        "transactions": [transaction_to_dict(t) for t in event.transactions],
                    })
                case InputRequired():
                    task, pending = event.task, event
                case TaskCompleted():
                    task = event.task
                case TaskFailed():
                    raise ReviewError(f"{name} {event.message}")
        if task is None:
            raise ReviewError(f"{name}: stream ended without completing or asking for input")
        return {"transactions": fetched, "tasks": {name: task}, "pending_remote": {name: pending}}

    async def reconcile(state: ReviewState) -> dict[str, Any]:
        merchants = {merchant_key(t.raw_merchant) for t in state["transactions"]}
        known = await deps.memory.lookup(state["user_id"], merchants)
        transactions = apply_memory(state["transactions"], known)
        current = await publish_totals(transactions, list(state["skipped"]))
        return {"transactions": transactions, "totals": current}

    async def pose(state: ReviewState) -> dict[str, Any]:
        """Kept apart from ask so a resumed ask, which reruns from its start, never re-emits."""
        unsure = {
            key: rows
            for key, rows in unsure_merchants(state["transactions"]).items()
            if key not in state["left_unanswered"]
        }
        questions = build_questions(unsure, state["pending_remote"], deps.agents)
        if not questions:
            return {"questions": [], "resume_agents": []}
        await emit(REVIEW_QUESTION, interrupt_payload(questions))
        return {"questions": questions}

    async def ask(state: ReviewState) -> dict[str, Any]:
        """Pause for answers to the posed questions and apply them.

        The runner validates answers before resuming. An invalid answer set that still arrives
        here fails the review: InvalidAnswersError propagates out of ainvoke, and LangGraph keeps
        the rejected answers, replaying them on any later resume of the thread.
        """
        questions = state["questions"]
        if not questions:
            return {}
        raw = interrupt(interrupt_payload(questions))
        answers = validate_answers(questions, raw["answers"])
        for key, category in answers.categories.items():
            await deps.memory.remember(state["user_id"], key, category)
        newly_skipped = [a for a, action in answers.remote.items() if action == SKIP]
        update: dict[str, Any] = {
            "resume_agents": [a for a, action in answers.remote.items() if action == CONTINUE],
            "skipped": {a: True for a in newly_skipped},
            "pending_remote": {a: None for a in answers.remote},
            "left_unanswered": {
                q.merchant_key: True
                for q in questions
                if isinstance(q, CategorizeQuestion) and q.merchant_key not in answers.categories
            },
            "questions": [],
        }
        if answers.categories or newly_skipped:
            transactions = apply_memory(state["transactions"], answers.categories)
            update["transactions"] = transactions
            update["totals"] = await publish_totals(
                transactions, [*state["skipped"], *newly_skipped]
            )
        return update

    async def recategorize(state: ReviewState) -> dict[str, Any]:
        chosen = state["recategorize"]
        for key, category in chosen.items():
            await deps.memory.remember(state["user_id"], key, category)
        transactions = apply_memory(state["transactions"], chosen)
        current = await publish_totals(transactions, list(state["skipped"]))
        return {"transactions": transactions, "totals": current, "recategorize": {}}

    async def report(state: ReviewState) -> dict[str, Any]:
        prompt = report_prompt(
            state["month"],
            deps.budget.currency,
            state["totals"],
            len(state["transactions"]),
            list(state["skipped"]),
        )
        await emit(REVIEW_WRITING, {})
        text = await deps.report_writer.write(prompt)
        await emit(REVIEW_REPORT, {"text": text})
        return {"report": text}

    builder = StateGraph(ReviewState)
    builder.add_node("discover", discover)
    builder.add_node("fetch_agent", fetch_agent, input_schema=FetchRequest)
    builder.add_node("reconcile", reconcile)
    builder.add_node("pose", pose)
    builder.add_node("ask", ask)
    builder.add_node("recategorize", recategorize)
    builder.add_node("report", report)
    builder.add_conditional_edges(START, route_start, ["discover", "recategorize"])
    builder.add_conditional_edges("discover", fan_out, ["fetch_agent"])
    builder.add_edge("fetch_agent", "reconcile")
    builder.add_edge("reconcile", "pose")
    builder.add_edge("pose", "ask")
    builder.add_conditional_edges("ask", route_after_ask, ["fetch_agent", "report"])
    builder.add_edge("recategorize", "report")
    builder.add_edge("report", END)
    return builder.compile(checkpointer=checkpointer)
