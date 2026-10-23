import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import structlog.testing

from hfm.domain.errors import InvalidAnswersError
from hfm.domain.events import REVIEW_FAILED, REVIEW_QUESTION, REVIEW_REPORT, REVIEW_STATUS
from hfm.domain.models import Review, ReviewStatus
from hfm.platform.app import AppDeps
from hfm.platform.review_runner import (
    DAILY_REVIEW_LIMIT,
    INTERRUPTED_MESSAGE,
    REVIEW_LIMIT_WINDOW,
    DailyLimitError,
    MonthReviewedError,
    ReviewConflictError,
    ReviewNotFoundError,
    ReviewRunner,
)
from hfm.ports import CardAgentClient, TaskFailed
from tests.builders import make_tx
from tests.platform.support import (
    CATEGORY_QUESTION,
    COMPLETED,
    DANA,
    DANA_TOKEN,
    GROCERIES,
    MONTH,
    NOAM,
    NOAM_TOKEN,
    OTHER_MONTH,
    REMOTE_QUESTION,
    REPORT,
    UNKNOWN_KEY,
    UNKNOWN_MERCHANT,
    UNKNOWN_MERCHANT_AND_CODE,
    WORKING,
    BlockedCardClient,
    BrokenCardClient,
    UnusableCardClient,
    app_deps,
    batch,
    failed_event,
    scripted,
)


class Run:
    def __init__(self, deps: AppDeps) -> None:
        self.deps = deps
        self.runner = ReviewRunner(
            deps.graph, deps.reviews, deps.sink, settle_seconds=SETTLE_SECONDS
        )

    async def event_types(self, review_id: str) -> list[str]:
        return [event.type for _, event in await self.deps.events.list(review_id)]


SETTLE_SECONDS = 0.2
NewRun = Callable[[CardAgentClient], Run]


@pytest.fixture
async def new_run() -> AsyncIterator[NewRun]:
    """Builds runs over fresh fakes and cancels whatever they still run at teardown."""
    runs: list[Run] = []

    def build(client: CardAgentClient) -> Run:
        runs.append(Run(app_deps(client)))
        return runs[-1]

    yield build
    for run in runs:
        await run.runner.aclose()


async def test_start_waits_with_the_posed_question(new_run: NewRun) -> None:
    run = new_run(scripted(UNKNOWN_MERCHANT))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    view = await run.runner.status(DANA, review_id)
    assert view.status == ReviewStatus.WAITING
    assert view.month == MONTH
    assert [q["id"] for q in view.questions] == [CATEGORY_QUESTION]
    assert view.questions[0]["kind"] == "categorize"
    assert view.report is None
    assert REVIEW_QUESTION in await run.event_types(review_id)


async def test_a_missing_remote_answer_is_rejected_and_the_graph_stays_resumable(
    new_run: NewRun,
) -> None:
    client = scripted(UNKNOWN_MERCHANT_AND_CODE)
    run = new_run(client)
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()
    fetches = len(client.calls)

    with pytest.raises(InvalidAnswersError) as rejected:
        await run.runner.answer(DANA, review_id, {CATEGORY_QUESTION: "dining"}, DANA_TOKEN)
    await run.runner.drain()

    assert rejected.value.missing == [REMOTE_QUESTION]
    assert len(client.calls) == fetches
    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.WAITING

    await run.runner.answer(
        DANA, review_id, {CATEGORY_QUESTION: "dining", REMOTE_QUESTION: "skip"}, DANA_TOKEN
    )
    await run.runner.drain()
    view = await run.runner.status(DANA, review_id)
    assert view.status == ReviewStatus.COMPLETED
    assert view.skipped == ["amex"]


async def test_full_answers_complete_the_review_with_a_report(new_run: NewRun) -> None:
    run = new_run(scripted(UNKNOWN_MERCHANT))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    await run.runner.answer(DANA, review_id, {CATEGORY_QUESTION: "dining"}, DANA_TOKEN)
    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.RUNNING
    await run.runner.drain()

    view = await run.runner.status(DANA, review_id)
    assert view.status == ReviewStatus.COMPLETED
    assert view.report == REPORT
    assert view.questions == []
    assert view.skipped == []
    assert {t.category for t in view.totals} == {"groceries", "dining"}
    assert (await run.event_types(review_id))[-2:] == [REVIEW_REPORT, REVIEW_STATUS]


async def test_every_status_change_after_the_start_is_logged_after_the_runs_events(
    new_run: NewRun,
) -> None:
    run = new_run(scripted(UNKNOWN_MERCHANT))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()
    await run.runner.answer(DANA, review_id, {CATEGORY_QUESTION: "dining"}, DANA_TOKEN)
    await run.runner.drain()

    events = [event for _, event in await run.deps.events.list(review_id)]
    statuses = [e.data["status"] for e in events if e.type == REVIEW_STATUS]
    assert statuses == ["waiting", "running", "completed"]
    types = [e.type for e in events]
    assert types.index(REVIEW_QUESTION) < types.index(REVIEW_STATUS)


async def test_answers_sent_right_after_the_question_wait_for_the_pausing_run(
    new_run: NewRun,
) -> None:
    run = new_run(scripted(UNKNOWN_MERCHANT))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    assert (await run.runner.status(DANA, review_id)).questions == []

    await run.runner.answer(DANA, review_id, {CATEGORY_QUESTION: "dining"}, DANA_TOKEN)
    await run.runner.drain()

    view = await run.runner.status(DANA, review_id)
    assert view.status == ReviewStatus.COMPLETED
    assert view.report == REPORT


async def test_domain_failure_reaches_the_user_verbatim(new_run: NewRun) -> None:
    run = new_run(UnusableCardClient())
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.FAILED
    events = await run.deps.events.list(review_id)
    assert events[-1][1] == failed_event("amex does not advertise the skill")


async def test_an_agent_task_failure_reaches_the_user_verbatim(new_run: NewRun) -> None:
    run = new_run(scripted([WORKING, TaskFailed("amex", "statement file is unreadable")]))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.FAILED
    events = await run.deps.events.list(review_id)
    assert events[-1][1] == failed_event("amex statement file is unreadable")


async def test_infrastructure_failure_hides_its_detail_and_logs_it(new_run: NewRun) -> None:
    run = new_run(BrokenCardClient())
    with structlog.testing.capture_logs() as logged:
        review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
        await run.runner.drain()

    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.FAILED
    events = await run.deps.events.list(review_id)
    assert events[-1][1] == failed_event("ConnectionError: see the server log")
    [failure] = [entry for entry in logged if entry["log_level"] == "error"]
    assert "10.0.0.5" in str(failure["exc_info"])


async def test_answering_a_run_that_does_not_settle_is_refused(new_run: NewRun) -> None:
    run = new_run(BlockedCardClient())
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)

    with pytest.raises(ReviewConflictError, match="still running"):
        await run.runner.answer(DANA, review_id, {}, DANA_TOKEN)
    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.RUNNING


async def test_unknown_review_is_not_found(new_run: NewRun) -> None:
    run = new_run(scripted())
    with pytest.raises(ReviewNotFoundError):
        await run.runner.status(DANA, "missing")
    with pytest.raises(KeyError):
        await run.runner.answer(DANA, "missing", {}, DANA_TOKEN)


async def test_aclose_cancels_running_reviews(new_run: NewRun) -> None:
    client = BlockedCardClient()
    run = new_run(client)
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await asyncio.wait_for(client.entered.wait(), timeout=5)

    await run.runner.aclose()
    await run.runner.drain()

    assert client.cancelled
    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.RUNNING
    assert REVIEW_FAILED not in await run.event_types(review_id)


async def test_fail_interrupted_fails_running_reviews_and_leaves_waiting_ones(
    new_run: NewRun,
) -> None:
    run = new_run(scripted())
    stamp = datetime(2026, 10, 1, tzinfo=UTC)
    await run.deps.reviews.add(Review("r-running", DANA.id, MONTH, ReviewStatus.RUNNING, stamp))
    await run.deps.reviews.add(
        Review("r-waiting", DANA.id, OTHER_MONTH, ReviewStatus.WAITING, stamp)
    )

    await run.runner.fail_interrupted()

    assert (await run.deps.reviews.get("r-running")).status == ReviewStatus.FAILED
    assert await run.deps.events.list("r-running") == [
        (1, failed_event(INTERRUPTED_MESSAGE))
    ]
    assert (await run.deps.reviews.get("r-waiting")).status == ReviewStatus.WAITING
    assert await run.deps.events.list("r-waiting") == []


async def test_recategorizing_a_completed_review_reruns_it_to_a_new_report(
    new_run: NewRun,
) -> None:
    run = new_run(scripted(UNKNOWN_MERCHANT))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()
    await run.runner.answer(DANA, review_id, {CATEGORY_QUESTION: "dining"}, DANA_TOKEN)
    await run.runner.drain()

    await run.runner.recategorize(DANA, review_id, {UNKNOWN_KEY: "health"})
    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.RUNNING
    await run.runner.drain()

    view = await run.runner.status(DANA, review_id)
    assert view.status == ReviewStatus.COMPLETED
    assert {t.category for t in view.totals} == {"groceries", "health"}
    assert (await run.event_types(review_id)).count(REVIEW_REPORT) == 2


async def test_recategorizing_a_review_that_is_not_completed_is_refused(new_run: NewRun) -> None:
    run = new_run(scripted(UNKNOWN_MERCHANT))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    with pytest.raises(ReviewConflictError, match="not completed"):
        await run.runner.recategorize(DANA, review_id, {UNKNOWN_KEY: "health"})


async def test_recategorizing_an_unknown_merchant_leaves_the_review_completed(
    new_run: NewRun,
) -> None:
    run = new_run(scripted([batch(GROCERIES), COMPLETED]))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    with pytest.raises(InvalidAnswersError) as rejected:
        await run.runner.recategorize(DANA, review_id, {"nobody": "health"})
    assert rejected.value.unknown == ["nobody"]
    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.COMPLETED


async def test_a_month_with_a_standing_review_cannot_start_again(new_run: NewRun) -> None:
    run = new_run(scripted([batch(GROCERIES), COMPLETED]))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    with pytest.raises(MonthReviewedError) as refused:
        await run.runner.start(DANA, MONTH, DANA_TOKEN)
    assert refused.value.review_id == review_id


async def test_clearing_a_review_frees_its_month_and_hides_it(new_run: NewRun) -> None:
    run = new_run(scripted([batch(GROCERIES), COMPLETED], [batch(GROCERIES), COMPLETED]))
    cleared_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    await run.runner.clear(DANA, cleared_id)

    with pytest.raises(ReviewNotFoundError, match="was cleared"):
        await run.runner.status(DANA, cleared_id)
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()
    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.COMPLETED


async def test_a_running_review_cannot_be_cleared(new_run: NewRun) -> None:
    run = new_run(BlockedCardClient())
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)

    with pytest.raises(ReviewConflictError, match="still running"):
        await run.runner.clear(DANA, review_id)
    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.RUNNING


async def test_starts_beyond_the_daily_limit_are_refused_cleared_ones_included(
    new_run: NewRun,
) -> None:
    run = new_run(BlockedCardClient())
    now = datetime.now(UTC)
    for n in range(DAILY_REVIEW_LIMIT):
        stamp = now - REVIEW_LIMIT_WINDOW + timedelta(hours=n + 1)
        await run.deps.reviews.add(
            Review(f"r-{n}", DANA.id, f"2025-0{n + 1}", ReviewStatus.FAILED, stamp)
        )
        await run.runner.clear(DANA, f"r-{n}")

    with pytest.raises(DailyLimitError) as refused:
        await run.runner.start(DANA, MONTH, DANA_TOKEN)
    assert refused.value.next_start == now + timedelta(hours=1)


async def test_starts_older_than_the_window_do_not_count(new_run: NewRun) -> None:
    run = new_run(BlockedCardClient())
    stale = datetime.now(UTC) - REVIEW_LIMIT_WINDOW - timedelta(minutes=1)
    for n in range(DAILY_REVIEW_LIMIT):
        await run.deps.reviews.add(
            Review(f"r-{n}", DANA.id, f"2025-0{n + 1}", ReviewStatus.FAILED, stale)
        )

    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)

    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.RUNNING


async def test_the_month_view_names_the_standing_review_and_the_starts_left(
    new_run: NewRun,
) -> None:
    run = new_run(scripted([batch(GROCERIES), COMPLETED]))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    reviewed = await run.runner.month(DANA, MONTH)
    assert reviewed.review is not None and reviewed.review.id == review_id
    assert reviewed.starts_left == DAILY_REVIEW_LIMIT - 1
    assert reviewed.next_start is None
    assert (await run.runner.month(DANA, OTHER_MONTH)).review is None


async def test_the_month_view_says_when_the_next_start_is_allowed(new_run: NewRun) -> None:
    run = new_run(scripted())
    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    for n in range(DAILY_REVIEW_LIMIT):
        await run.deps.reviews.add(
            Review(f"r-{n}", DANA.id, f"2025-0{n + 1}", ReviewStatus.FAILED, an_hour_ago)
        )

    view = await run.runner.month(DANA, MONTH)

    assert view.starts_left == 0
    assert view.next_start == an_hour_ago + REVIEW_LIMIT_WINDOW


async def test_another_persons_review_is_not_found_and_their_month_is_free(new_run: NewRun) -> None:
    run = new_run(scripted([batch(GROCERIES), COMPLETED], [batch(GROCERIES), COMPLETED]))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    with pytest.raises(ReviewNotFoundError):
        await run.runner.status(NOAM, review_id)
    with pytest.raises(ReviewNotFoundError):
        await run.runner.clear(NOAM, review_id)
    assert (await run.runner.month(NOAM, MONTH)).review is None

    theirs = await run.runner.start(NOAM, MONTH, NOAM_TOKEN)
    await run.runner.drain()
    assert theirs != review_id
    assert (await run.runner.status(NOAM, theirs)).status == ReviewStatus.COMPLETED
    assert (await run.runner.status(DANA, review_id)).status == ReviewStatus.COMPLETED


async def test_the_daily_limit_counts_each_persons_own_starts(new_run: NewRun) -> None:
    run = new_run(BlockedCardClient())
    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    for n in range(DAILY_REVIEW_LIMIT):
        await run.deps.reviews.add(
            Review(f"r-{n}", DANA.id, f"2025-0{n + 1}", ReviewStatus.FAILED, an_hour_ago)
        )

    with pytest.raises(DailyLimitError):
        await run.runner.start(DANA, MONTH, DANA_TOKEN)
    assert (await run.runner.month(NOAM, MONTH)).starts_left == DAILY_REVIEW_LIMIT
    review_id = await run.runner.start(NOAM, MONTH, NOAM_TOKEN)
    assert (await run.runner.status(NOAM, review_id)).status == ReviewStatus.RUNNING


async def test_each_fetch_forwards_the_token_of_the_request_that_started_it(
    new_run: NewRun,
) -> None:
    client = scripted(UNKNOWN_MERCHANT_AND_CODE, [batch(GROCERIES), COMPLETED])
    run = new_run(client)
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    await run.runner.answer(
        DANA, review_id, {CATEGORY_QUESTION: "dining", REMOTE_QUESTION: "continue"}, "tok-fresh"
    )
    await run.runner.drain()

    assert client.tokens == [DANA_TOKEN, "tok-fresh"]


async def test_expected_charges_project_the_latest_earlier_reviews_standing_orders(
    new_run: NewRun,
) -> None:
    gym = make_tx(id="9", raw_merchant="וים קלאבס", category="health", standing_order=True)
    run = new_run(scripted([batch(GROCERIES, gym), COMPLETED], [batch(GROCERIES), COMPLETED]))
    await run.runner.start(DANA, OTHER_MONTH, DANA_TOKEN)
    await run.runner.drain()
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    view = await run.runner.expected(DANA, review_id)

    assert view.based_on == OTHER_MONTH
    assert [t.id for t in view.transactions] == ["expected-9"]
    assert {t.category: t.spent for t in view.totals} == {
        "groceries": GROCERIES.amount, "health": gym.amount,
    }
    assert view.standing_orders == gym.amount


async def test_expected_charges_without_an_earlier_review_are_the_actual_totals(
    new_run: NewRun,
) -> None:
    run = new_run(scripted([batch(GROCERIES), COMPLETED]))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    view = await run.runner.expected(DANA, review_id)

    assert view.based_on is None
    assert view.transactions == []
    assert view.totals == (await run.runner.status(DANA, review_id)).totals
    assert view.standing_orders == Decimal(0)


async def test_expected_charges_of_a_review_that_is_not_completed_are_refused(
    new_run: NewRun,
) -> None:
    run = new_run(scripted(UNKNOWN_MERCHANT))
    review_id = await run.runner.start(DANA, MONTH, DANA_TOKEN)
    await run.runner.drain()

    with pytest.raises(ReviewConflictError, match="not completed"):
        await run.runner.expected(DANA, review_id)
