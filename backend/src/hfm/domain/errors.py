"""Failures the review reports to its callers."""
from __future__ import annotations


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
