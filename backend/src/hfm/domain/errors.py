"""Failures the review reports to its callers."""
from __future__ import annotations

from hfm.domain.models import ReviewStatus


class ReviewError(Exception):
    pass


class AgentUnusableError(ReviewError):
    """Read by the person as "<agent> <reason>", so the reason is a predicate: "could not be
    reached at ...", "advertises no JSON-RPC interface"."""

    def __init__(self, agent: str, reason: str) -> None:
        super().__init__(f"{agent} {reason}")
        self.agent = agent
        self.reason = reason


class InvalidAnswersError(ReviewError):
    def __init__(
        self, missing: list[str], unknown: list[str], invalid: dict[str, str]
    ) -> None:
        super().__init__(
            f"invalid answers: missing={missing}, unknown={unknown}, invalid={invalid}"
        )
        self.missing = missing
        self.unknown = unknown
        self.invalid = invalid


class InvalidTokenError(Exception):
    """An ID token that fails verification; the reason is written for the person who sent it."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class StaleStatusError(Exception):
    """A write refused because the review's status or clearing moved on since it was read."""

    def __init__(self, review_id: str, status: ReviewStatus, cleared: bool) -> None:
        state = "cleared" if cleared else status
        super().__init__(f"review {review_id!r} is {state}")
        self.review_id = review_id
        self.status = status
        self.cleared = cleared
