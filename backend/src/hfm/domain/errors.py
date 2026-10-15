"""Failures the review reports to its callers."""
from __future__ import annotations


class ReviewError(Exception):
    pass


class AgentUnusableError(ReviewError):
    def __init__(self, agent: str, reason: str) -> None:
        super().__init__(f"agent '{agent}' is unusable: {reason}")
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
