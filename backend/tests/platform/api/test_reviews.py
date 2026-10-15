from collections.abc import Awaitable, Callable, Iterator
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hfm.domain.models import Review, ReviewStatus
from hfm.platform.app import AppDeps, create_app
from hfm.platform.review_runner import DAILY_REVIEW_LIMIT, ReviewRunner
from hfm.ports import CardAgentClient
from tests.platform.support import (
    CATEGORY_QUESTION,
    COMPLETED,
    GROCERIES,
    MONTH,
    REMOTE_QUESTION,
    REPORT,
    UNKNOWN_KEY,
    UNKNOWN_MERCHANT,
    UNKNOWN_MERCHANT_AND_CODE,
    app_deps,
    batch,
    scripted,
)


class Api:
    """A TestClient over the app; background review runs are awaited through drain()."""

    def __init__(self, client: TestClient, deps: AppDeps) -> None:
        self.client = client
        self.deps = deps

    def call(self, fn: Callable[..., Awaitable[Any]], *args: Any) -> Any:
        """Run a coroutine on the app's event loop, where its background runs live."""
        assert self.client.portal is not None, "the client is entered, so its loop runs"
        return self.client.portal.call(fn, *args)

    def drain(self) -> None:
        app = self.client.app
        assert isinstance(app, FastAPI)
        runner: ReviewRunner = app.state.runner
        self.call(runner.drain)

    def start(self) -> str:
        response = self.client.post("/api/reviews", json={"month": MONTH})
        assert response.status_code == 202
        review_id: str = response.json()["id"]
        self.drain()
        return review_id


NewApi = Callable[[CardAgentClient], Api]


@pytest.fixture
def new_api() -> Iterator[NewApi]:
    """Entered clients keep one event loop and run the app's lifespan around the test."""
    with ExitStack() as stack:

        def build(card_client: CardAgentClient) -> Api:
            deps = app_deps(card_client)
            client = stack.enter_context(TestClient(create_app(deps=deps)))
            return Api(client, deps)

        yield build


def test_start_returns_202_with_the_review_id(new_api: NewApi) -> None:
    api = new_api(scripted(UNKNOWN_MERCHANT))
    review_id = api.start()

    body = api.client.get(f"/api/reviews/{review_id}").json()
    assert body["id"] == review_id
    assert body["month"] == MONTH
    assert body["status"] == "waiting"
    assert "createdAt" in body
    assert [q["id"] for q in body["questions"]] == [CATEGORY_QUESTION]
    assert body["report"] is None


@pytest.mark.parametrize("month", ["2026-13", "2026-9", "September", ""])
def test_start_rejects_a_malformed_month(new_api: NewApi, month: str) -> None:
    api = new_api(scripted())
    assert api.client.post("/api/reviews", json={"month": month}).status_code == 422


def test_unknown_review_is_404(new_api: NewApi) -> None:
    api = new_api(scripted())
    assert api.client.get("/api/reviews/missing").status_code == 404
    answered = api.client.post("/api/reviews/missing/answers", json={"answers": {}})
    assert answered.status_code == 404
    assert api.client.get("/api/reviews/missing/events").status_code == 404


def test_answering_a_review_that_is_not_waiting_is_409(new_api: NewApi) -> None:
    api = new_api(scripted())
    running = Review("r-running", MONTH, ReviewStatus.RUNNING, datetime.now(UTC))
    api.call(api.deps.reviews.add, running)

    response = api.client.post("/api/reviews/r-running/answers", json={"answers": {}})
    assert response.status_code == 409


def test_partial_answers_are_422_with_what_is_wrong(new_api: NewApi) -> None:
    api = new_api(scripted(UNKNOWN_MERCHANT_AND_CODE))
    review_id = api.start()

    response = api.client.post(
        f"/api/reviews/{review_id}/answers",
        json={"answers": {CATEGORY_QUESTION: "not-a-category", "extra": "x"}},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["missing"] == [REMOTE_QUESTION]
    assert detail["unknown"] == ["extra"]
    assert CATEGORY_QUESTION in detail["invalid"]
    assert api.client.get(f"/api/reviews/{review_id}").json()["status"] == "waiting"


def test_full_answers_are_204_and_complete_the_review(new_api: NewApi) -> None:
    api = new_api(scripted(UNKNOWN_MERCHANT))
    review_id = api.start()

    response = api.client.post(
        f"/api/reviews/{review_id}/answers", json={"answers": {CATEGORY_QUESTION: "dining"}}
    )
    assert response.status_code == 204
    api.drain()

    body = api.client.get(f"/api/reviews/{review_id}").json()
    assert body["status"] == "completed"
    assert body["report"] == REPORT
    assert body["questions"] == []
    groceries = next(t for t in body["totals"] if t["category"] == "groceries")
    assert groceries == {
        "category": "groceries", "spent": "86.90", "limit": "500.00", "over": False,
    }


def test_recategorizing_is_204_for_a_completed_review_and_409_otherwise(new_api: NewApi) -> None:
    api = new_api(scripted(UNKNOWN_MERCHANT))
    review_id = api.start()
    body = {"categories": {UNKNOWN_KEY: "health"}}

    assert api.client.post(f"/api/reviews/{review_id}/categories", json=body).status_code == 409
    api.client.post(f"/api/reviews/{review_id}/answers", json={"answers": {}})
    api.drain()

    assert api.client.post(f"/api/reviews/{review_id}/categories", json=body).status_code == 204
    api.drain()
    totals = api.client.get(f"/api/reviews/{review_id}").json()["totals"]
    assert {t["category"] for t in totals if t["spent"] != "0.00"} == {"groceries", "health"}


def test_recategorizing_with_no_categories_or_an_unknown_merchant_is_422(new_api: NewApi) -> None:
    api = new_api(scripted(UNKNOWN_MERCHANT))
    review_id = api.start()
    api.client.post(f"/api/reviews/{review_id}/answers", json={"answers": {}})
    api.drain()
    url = f"/api/reviews/{review_id}/categories"

    assert api.client.post(url, json={"categories": {}}).status_code == 422
    unknown = api.client.post(url, json={"categories": {"nobody": "health"}})
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["unknown"] == ["nobody"]


def test_starting_a_month_that_has_a_review_is_409_naming_it(new_api: NewApi) -> None:
    api = new_api(scripted([batch(GROCERIES), COMPLETED]))
    review_id = api.start()

    response = api.client.post("/api/reviews", json={"month": MONTH})
    assert response.status_code == 409
    assert response.json()["detail"]["reviewId"] == review_id
    assert "clear it" in response.json()["detail"]["message"]


def test_a_cleared_review_is_404_and_its_month_starts_anew(new_api: NewApi) -> None:
    api = new_api(scripted([batch(GROCERIES), COMPLETED], [batch(GROCERIES), COMPLETED]))
    cleared_id = api.start()

    assert api.client.delete(f"/api/reviews/{cleared_id}").status_code == 204
    assert api.client.get(f"/api/reviews/{cleared_id}").status_code == 404
    assert api.client.delete(f"/api/reviews/{cleared_id}").status_code == 404
    assert api.start() != cleared_id


def test_a_start_beyond_the_daily_limit_is_429_with_retry_after(new_api: NewApi) -> None:
    api = new_api(scripted())
    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    for n in range(DAILY_REVIEW_LIMIT):
        review = Review(f"r-{n}", f"2025-0{n + 1}", ReviewStatus.FAILED, an_hour_ago)
        api.call(api.deps.reviews.add, review)

    response = api.client.post("/api/reviews", json={"month": MONTH})
    assert response.status_code == 429
    assert 0 < int(response.headers["Retry-After"]) <= 23 * 3600


def test_the_month_route_names_its_review_and_the_starts_left(new_api: NewApi) -> None:
    api = new_api(scripted([batch(GROCERIES), COMPLETED]))
    review_id = api.start()

    body = api.client.get(f"/api/months/{MONTH}").json()
    assert body == {
        "month": MONTH,
        "review": {"id": review_id, "status": "completed"},
        "limit": DAILY_REVIEW_LIMIT,
        "startsLeft": DAILY_REVIEW_LIMIT - 1,
        "nextStart": None,
    }
    assert api.client.get("/api/months/2026-13").status_code == 422
