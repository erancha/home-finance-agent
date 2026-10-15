"""Request and response bodies of the review API; money is rendered as decimal strings."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from hfm.domain.events import total_to_dict
from hfm.domain.models import ReviewStatus
from hfm.platform.review_runner import MonthView, ReviewView

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class StartReviewRequest(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN, examples=["2026-09"])


class StartReviewResponse(BaseModel):
    id: str


class AnswersRequest(BaseModel):
    answers: dict[str, Any]
    """Question id to the chosen value; validated against the posed questions, not here."""


class CategoriesRequest(BaseModel):
    categories: dict[str, Any] = Field(min_length=1)
    """Merchant key to category; validated against the review's merchants, not here."""


class ReviewResponse(BaseModel):
    id: str
    month: str
    status: ReviewStatus
    created_at: datetime = Field(serialization_alias="createdAt")
    questions: list[dict[str, Any]]
    totals: list[dict[str, Any]]
    skipped: list[str]
    report: str | None

    @classmethod
    def from_view(cls, view: ReviewView) -> ReviewResponse:
        return cls(
            id=view.id,
            month=view.month,
            status=view.status,
            created_at=view.created_at,
            questions=view.questions,
            totals=[total_to_dict(t) for t in view.totals],
            skipped=view.skipped,
            report=view.report,
        )


class StandingReview(BaseModel):
    id: str
    status: ReviewStatus


class MonthResponse(BaseModel):
    month: str
    review: StandingReview | None
    limit: int
    starts_left: int = Field(serialization_alias="startsLeft")
    next_start: datetime | None = Field(serialization_alias="nextStart")

    @classmethod
    def from_view(cls, view: MonthView) -> MonthResponse:
        review = view.review
        return cls(
            month=view.month,
            review=None if review is None else StandingReview(id=review.id, status=review.status),
            limit=view.limit,
            starts_left=view.starts_left,
            next_start=view.next_start,
        )
