"""Starts review graphs, resumes them with validated answers and reports their state.

Core building blocks:
- ReviewRunner: start, answer, recategorize, clear, status, expected and month for the API, each on
  behalf of the signed-in person; every graph invocation runs as a background task so a request
  returns as soon as the review is recorded
- ReviewView: a review's record joined with what its checkpoint knows (questions, totals, report)
- ExpectedView: a completed review's totals with the charges it still expects added
- MonthView: whether a month has a standing review and whether a review may start now
- ReviewNotFoundError, ReviewConflictError, MonthReviewedError, DailyLimitError: the refusals the
  API maps to 404, 409, 409 and 429; a conflict is a review whose status does not allow the request

Every start fetches from the card agents and, unless the person's report memory holds the text
for the same totals, has a model write the report, so starts are rationed per person: a person's
month has one standing review until they clear it, and at most DAILY_REVIEW_LIMIT of their reviews
start in any REVIEW_LIMIT_WINDOW, cleared ones included. A cleared review is gone to the API, and
so is another person's review: both are not found.

A run that reaches a card agent carries the person's ID token in a run-scoped context variable,
set around the invocation and never written anywhere.

A review's status follows its latest invocation: RUNNING while one is in flight, WAITING when it
stopped at the question interrupt, COMPLETED when the graph reached its end, FAILED when it
raised. Recategorizing a COMPLETED review runs it again, back to COMPLETED. A review has at most
one invocation in flight. The review id is the checkpoint thread id. A review still RUNNING when a
new process starts lost its invocation and is failed. A RUNNING review cannot be cleared.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from hfm.application.event_sink import ReviewEventSink
from hfm.application.expected import expected_charges, with_expected
from hfm.application.questions import validate_answers, validate_categories
from hfm.application.reconcile import standing_orders
from hfm.application.review_graph import ReviewState
from hfm.application.user_token import with_user_token
from hfm.domain.errors import ReviewError
from hfm.domain.events import REVIEW_FAILED, ReviewEvent
from hfm.domain.models import CategoryTotal, Review, ReviewStatus, Transaction, User
from hfm.ports import ReviewRepository

log = structlog.get_logger(__name__)

SETTLE_SECONDS = 30.0
"""How long an answer waits for the review's in-flight run to reach its pause."""

DAILY_REVIEW_LIMIT = 5
REVIEW_LIMIT_WINDOW = timedelta(hours=24)

INTERRUPTED_MESSAGE = "interrupted by a server restart; clear the review and start it again"

ReviewGraph = CompiledStateGraph[ReviewState, None, ReviewState, ReviewState]


class ReviewNotFoundError(KeyError):
    def __init__(self, review_id: str, reason: str = "does not exist") -> None:
        super().__init__(f"review {review_id!r} {reason}")
        self.review_id = review_id


class ReviewConflictError(Exception):
    def __init__(self, review_id: str, status: ReviewStatus, reason: str) -> None:
        super().__init__(f"review {review_id!r} is {status}: {reason}")
        self.review_id = review_id
        self.status = status


class MonthReviewedError(Exception):
    def __init__(self, month: str, review_id: str) -> None:
        super().__init__(f"{month} already has a review; clear it to start a new one")
        self.month = month
        self.review_id = review_id


class DailyLimitError(Exception):
    def __init__(self, limit: int, next_start: datetime) -> None:
        hours = REVIEW_LIMIT_WINDOW / timedelta(hours=1)
        super().__init__(
            f"{limit} reviews were started in the last {hours:g} hours; "
            f"the next can start at {next_start:%Y-%m-%d %H:%M} UTC"
        )
        self.next_start = next_start


@dataclass(frozen=True)
class ReviewView:
    id: str
    month: str
    status: ReviewStatus
    created_at: datetime
    questions: list[dict[str, Any]]
    """Wire form of the questions the review is paused on; empty unless it waits for answers."""
    totals: list[CategoryTotal]
    skipped: list[str]
    """Agents the user chose to leave out; the totals lack their spend."""
    report: str | None


@dataclass(frozen=True)
class ExpectedView:
    based_on: str | None
    """The month the expected charges are projected from; None when no earlier month has a
    completed review, and then nothing is expected."""
    transactions: list[Transaction]
    totals: list[CategoryTotal]
    """The review's totals with the expected spend added."""
    standing_orders: Decimal
    """The review's standing-order spend with the expected standing orders added."""


@dataclass(frozen=True)
class MonthView:
    month: str
    review: Review | None
    """The month's standing review; None when it has none."""
    limit: int
    starts_left: int
    """Starts left in the current REVIEW_LIMIT_WINDOW."""
    next_start: datetime | None
    """When a start is next allowed; None while starts are left."""


class ReviewRunner:
    def __init__(
        self,
        graph: ReviewGraph,
        reviews: ReviewRepository,
        sink: ReviewEventSink,
        settle_seconds: float = SETTLE_SECONDS,
        daily_limit: int = DAILY_REVIEW_LIMIT,
    ) -> None:
        self._graph = graph
        self._reviews = reviews
        self._sink = sink
        self._settle_seconds = settle_seconds
        self._daily_limit = daily_limit
        # Key: review id. Value: its in-flight invocation; a review has at most one, and the
        # strong reference keeps it from being garbage-collected.
        self._runs: dict[str, asyncio.Task[None]] = {}
        # Serializes a request's check and the write it allows, so one pause is resumed once, a
        # completed review is rerun once and concurrent starts cannot exceed the rations.
        self._status_lock = asyncio.Lock()

    async def start(self, user: User, month: str, token: str) -> str:
        """Raises MonthReviewedError when the person's month has a review that is not cleared,
        and DailyLimitError when their window's starts are used up."""
        async with self._status_lock:
            now = datetime.now(UTC)
            view = await self._month_view(user, month, now)
            if view.review is not None:
                raise MonthReviewedError(month, view.review.id)
            if view.next_start is not None:
                raise DailyLimitError(view.limit, view.next_start)
            review_id = str(uuid.uuid4())
            await self._reviews.add(Review(review_id, user.id, month, ReviewStatus.RUNNING, now))
        self._schedule(review_id, {"month": month, "user_id": user.id}, token)
        return review_id

    async def month(self, user: User, month: str) -> MonthView:
        return await self._month_view(user, month, datetime.now(UTC))

    async def _month_view(self, user: User, month: str, now: datetime) -> MonthView:
        standing = await self._reviews.standing_for_month(user.id, month)
        recent = await self._reviews.list_created_since(user.id, now - REVIEW_LIMIT_WINDOW)
        starts_left = max(self._daily_limit - len(recent), 0)
        next_start = None
        if starts_left == 0:
            # The start that frees a slot is the one whose expiry leaves limit - 1 inside.
            freeing = recent[len(recent) - self._daily_limit]
            next_start = freeing.created_at + REVIEW_LIMIT_WINDOW
        return MonthView(month, standing, self._daily_limit, starts_left, next_start)

    async def answer(
        self, user: User, review_id: str, answers: Mapping[str, Any], token: str
    ) -> None:
        """Resume the paused review; raises InvalidAnswersError, leaving it paused, when an answer
        names no posed question or holds an illegal value, or a remote question is unanswered.

        The question event goes out before the run reaches its pause, so an answer that arrives
        while the run is in flight waits for it to settle instead of being refused. The token is
        the one a continued fetch forwards, fresh from the person's current sign-in.
        """
        running = self._runs.get(review_id)
        if running is not None:
            settled, _ = await asyncio.wait({running}, timeout=self._settle_seconds)
            if not settled:
                raise ReviewConflictError(
                    review_id,
                    ReviewStatus.RUNNING,
                    f"still running after {self._settle_seconds:g} s, not waiting for answers",
                )
        async with self._status_lock:
            review = await self.review(user, review_id)
            if review.status != ReviewStatus.WAITING:
                raise ReviewConflictError(review_id, review.status, "not waiting for answers")
            snapshot = await self._graph.aget_state(_config(review_id))
            validate_answers(snapshot.values["questions"], answers)
            await self._reviews.set_status(review_id, ReviewStatus.RUNNING)
        self._schedule(review_id, Command(resume={"answers": dict(answers)}), token)

    async def recategorize(
        self, user: User, review_id: str, categories: Mapping[str, Any]
    ) -> None:
        """Rerun a completed review with categories chosen for its merchants: they are remembered,
        the totals recomputed and the report redone, from the report memory when the totals are
        unchanged. Raises InvalidAnswersError, leaving the review completed, for a merchant not in
        the review or an illegal category.
        """
        async with self._status_lock:
            review = await self.review(user, review_id)
            if review.status != ReviewStatus.COMPLETED:
                raise ReviewConflictError(review_id, review.status, "not completed")
            snapshot = await self._graph.aget_state(_config(review_id))
            chosen = validate_categories(snapshot.values["transactions"], categories)
            await self._reviews.set_status(review_id, ReviewStatus.RUNNING)
        # Recategorizing reaches no card agent, so the run needs no token.
        self._schedule(review_id, {"recategorize": chosen}, None)

    async def clear(self, user: User, review_id: str) -> None:
        """Free the review's month for a new review; the review is gone to the API afterwards.
        A RUNNING review is refused, since its invocation would go on writing to it."""
        async with self._status_lock:
            review = await self.review(user, review_id)
            if review.status == ReviewStatus.RUNNING:
                raise ReviewConflictError(review_id, review.status, "still running")
            await self._reviews.clear(review_id, datetime.now(UTC))

    async def status(self, user: User, review_id: str) -> ReviewView:
        review = await self.review(user, review_id)
        snapshot = await self._graph.aget_state(_config(review_id))
        # Nodes fill the state as the review progresses, so early on these keys are absent.
        values = snapshot.values
        # The interrupt is checkpointed before the run records WAITING; questions are offered
        # only once the run has settled, so they are never shown while answers would be refused.
        paused = bool(snapshot.interrupts) and review_id not in self._runs
        questions = snapshot.interrupts[0].value["questions"] if paused else []
        return ReviewView(
            id=review.id,
            month=review.month,
            status=review.status,
            created_at=review.created_at,
            questions=questions,
            totals=values.get("totals", []),
            skipped=list(values.get("skipped", {})),
            report=values.get("report"),
        )

    async def expected(self, user: User, review_id: str) -> ExpectedView:
        """The completed review's charges still expected from the person's latest completed review
        of an earlier month; reads only saved reviews and reaches no card agent."""
        review = await self.review(user, review_id)
        if review.status != ReviewStatus.COMPLETED:
            raise ReviewConflictError(review_id, review.status, "not completed")
        values = (await self._graph.aget_state(_config(review_id))).values
        actual: list[Transaction] = values["transactions"]
        base = await self._reviews.latest_completed_before(user.id, review.month)
        expected: list[Transaction] = []
        if base is not None:
            base_values = (await self._graph.aget_state(_config(base.id))).values
            expected = expected_charges(
                base_values["transactions"], base.month, actual, review.month
            )
        return ExpectedView(
            based_on=None if base is None else base.month,
            transactions=expected,
            totals=with_expected(values["totals"], expected),
            standing_orders=standing_orders([*actual, *expected]),
        )

    async def fail_interrupted(self) -> None:
        """Fail every review a stopped server left RUNNING; called before the runner serves.

        Its invocation died with the old process, so nothing would ever move it on. A WAITING
        review needs no process and is left to be answered.
        """
        assert not self._runs, "only a runner with no invocation in flight knows RUNNING is stale"
        for review in await self._reviews.list_by_status(ReviewStatus.RUNNING):
            log.warning("failing a review interrupted by a restart", review_id=review.id)
            await self._fail(review.id, INTERRUPTED_MESSAGE)

    async def review(self, user: User, review_id: str) -> Review:
        """The person's review unless it is unknown, another person's or cleared, all of which
        raise ReviewNotFoundError; another person's review looks exactly like an unknown one."""
        try:
            review = await self._reviews.get(review_id)
        except KeyError as error:
            raise ReviewNotFoundError(review_id) from error
        if review.user_id != user.id:
            raise ReviewNotFoundError(review_id)
        if review.cleared_at is not None:
            raise ReviewNotFoundError(review_id, "was cleared")
        return review

    async def drain(self) -> None:
        """Wait until no invocation is in flight, including ones scheduled while waiting."""
        while self._runs:
            await asyncio.wait(set(self._runs.values()))

    async def aclose(self) -> None:
        """Cancel in-flight invocations; their reviews stay RUNNING until the next startup's
        fail_interrupted."""
        runs = list(self._runs.values())
        for task in runs:
            task.cancel()
        await asyncio.gather(*runs, return_exceptions=True)

    def _schedule(
        self, review_id: str, graph_input: ReviewState | Command[Any], token: str | None
    ) -> None:
        assert review_id not in self._runs, f"review {review_id!r} already has a run in flight"
        task = asyncio.create_task(self._run(review_id, graph_input, token))
        self._runs[review_id] = task
        task.add_done_callback(lambda done: self._forget(review_id, done))

    async def _run(
        self, review_id: str, graph_input: ReviewState | Command[Any], token: str | None
    ) -> None:
        try:
            with with_user_token(token) if token is not None else nullcontext():
                result = await self._graph.ainvoke(graph_input, _config(review_id), version="v2")
        except Exception as error:
            log.error("review failed", review_id=review_id, exc_info=error)
            await self._fail(review_id, failure_message(error))
            return
        await self._reviews.set_status(
            review_id, ReviewStatus.WAITING if result.interrupts else ReviewStatus.COMPLETED
        )

    async def _fail(self, review_id: str, message: str) -> None:
        await self._reviews.set_status(review_id, ReviewStatus.FAILED)
        await self._sink.emit(review_id, ReviewEvent(REVIEW_FAILED, {"message": message}))

    def _forget(self, review_id: str, task: asyncio.Task[None]) -> None:
        """A run that raised while recording its own outcome is logged, never dropped silently."""
        assert self._runs[review_id] is task, "a review's runs never overlap"
        del self._runs[review_id]
        if not task.cancelled() and task.exception() is not None:
            log.error("review run crashed", exc_info=task.exception())


def failure_message(error: Exception) -> str:
    """ReviewError messages are written for the user; any other error's detail stays in the log."""
    if isinstance(error, ReviewError):
        return str(error)
    return f"{type(error).__name__}: see the server log"


def _config(review_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": review_id}}
