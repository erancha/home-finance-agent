"""Carries the signed-in person's ID token from the request to the A2A call of the same run.

The token rides in a context variable scoped to one graph invocation, not in the review state
and not in the run configuration, so no checkpoint or checkpoint metadata ever holds it. A node
that needs it reads current_user_token(); a run started without one cannot reach a card agent.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_user_token: ContextVar[str] = ContextVar("user_token")


@contextmanager
def with_user_token(token: str) -> Iterator[None]:
    reset = _user_token.set(token)
    try:
        yield
    finally:
        _user_token.reset(reset)


def current_user_token() -> str:
    """Raises LookupError outside with_user_token: a fetch without a person behind it is a bug."""
    return _user_token.get()
