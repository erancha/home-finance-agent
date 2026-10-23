"""REST routes that start reviews, report their state, accept answers to their questions,
recategorize the merchants of a completed review, project the charges a completed review still
expects, clear a review to free its month, and say whether a month has a review and whether one may
start; every one of them for the signed-in person."""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse

from hfm.domain.errors import InvalidAnswersError
from hfm.platform.api.auth import CurrentSession
from hfm.platform.api.schemas import (
    MONTH_PATTERN,
    AnswersRequest,
    CategoriesRequest,
    ExpectedResponse,
    MonthResponse,
    ReviewResponse,
    StartReviewRequest,
    StartReviewResponse,
)
from hfm.platform.dependencies import Runner
from hfm.platform.review_runner import (
    DailyLimitError,
    MonthReviewedError,
    ReviewConflictError,
    ReviewNotFoundError,
)

router = APIRouter(prefix="/api/reviews")
months_router = APIRouter(prefix="/api/months")


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_review(
    body: StartReviewRequest, runner: Runner, session: CurrentSession
) -> StartReviewResponse:
    return StartReviewResponse(id=await runner.start(session.user, body.month, session.token))


@router.get("/{review_id}")
async def get_review(review_id: str, runner: Runner, session: CurrentSession) -> ReviewResponse:
    return ReviewResponse.from_view(await runner.status(session.user, review_id))


@router.post("/{review_id}/answers", status_code=status.HTTP_204_NO_CONTENT)
async def answer_review(
    review_id: str, body: AnswersRequest, runner: Runner, session: CurrentSession
) -> Response:
    await runner.answer(session.user, review_id, body.answers, session.token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{review_id}/categories", status_code=status.HTTP_204_NO_CONTENT)
async def recategorize_review(
    review_id: str, body: CategoriesRequest, runner: Runner, session: CurrentSession
) -> Response:
    await runner.recategorize(session.user, review_id, body.categories)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{review_id}/expected")
async def expected_charges(
    review_id: str, runner: Runner, session: CurrentSession
) -> ExpectedResponse:
    return ExpectedResponse.from_view(await runner.expected(session.user, review_id))


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_review(review_id: str, runner: Runner, session: CurrentSession) -> Response:
    await runner.clear(session.user, review_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@months_router.get("/{month}")
async def get_month(
    month: Annotated[str, PathParam(pattern=MONTH_PATTERN)],
    runner: Runner,
    session: CurrentSession,
) -> MonthResponse:
    return MonthResponse.from_view(await runner.month(session.user, month))


def register_error_handlers(app: FastAPI) -> None:
    """Map the runner's refusals to 404, 409, 422 and 429 for every route."""

    async def not_found(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, ReviewNotFoundError)
        return JSONResponse({"detail": error.args[0]}, status_code=status.HTTP_404_NOT_FOUND)

    async def conflict(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, ReviewConflictError)
        return JSONResponse({"detail": str(error)}, status_code=status.HTTP_409_CONFLICT)

    async def month_reviewed(request: Request, error: Exception) -> JSONResponse:
        """Names the standing review so the page can open it instead."""
        assert isinstance(error, MonthReviewedError)
        detail = {"message": str(error), "reviewId": error.review_id}
        return JSONResponse({"detail": detail}, status_code=status.HTTP_409_CONFLICT)

    async def daily_limit(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, DailyLimitError)
        wait = math.ceil((error.next_start - datetime.now(UTC)).total_seconds())
        return JSONResponse(
            {"detail": str(error)},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(max(wait, 0))},
        )

    async def invalid_answers(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, InvalidAnswersError)
        detail = {"missing": error.missing, "unknown": error.unknown, "invalid": error.invalid}
        return JSONResponse(
            {"detail": detail}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
        )

    app.add_exception_handler(ReviewNotFoundError, not_found)
    app.add_exception_handler(ReviewConflictError, conflict)
    app.add_exception_handler(MonthReviewedError, month_reviewed)
    app.add_exception_handler(DailyLimitError, daily_limit)
    app.add_exception_handler(InvalidAnswersError, invalid_answers)
