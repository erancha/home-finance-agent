"""The ports and graph the HTTP app runs on, and the request dependencies that hand them out."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from hfm.application.event_sink import ReviewEventSink
from hfm.platform.review_runner import ReviewGraph, ReviewRunner
from hfm.ports import EventBus, Locks, ReviewEventStore, ReviewRepository, TokenVerifier


@dataclass(frozen=True)
class AppDeps:
    """Everything a request touches; production builds it from settings, tests from fakes."""

    reviews: ReviewRepository
    events: ReviewEventStore
    bus: EventBus
    sink: ReviewEventSink
    """Writes to events and publishes on bus; the graph emits through the same instance."""
    graph: ReviewGraph
    locks: Locks
    """Shared by every replica on the same database; the runner's run and start locks."""
    sessions: Callable[[], AsyncSession]
    """Opens database sessions; the readiness probe runs its query through it."""
    verifier: TokenVerifier
    """Checks the ID token behind every request."""
    google_client_id: str
    """The OAuth client the page signs people in with; published to the page, public."""
    card_agents: tuple[str, ...]
    """The registered card agents' names, in registry order; the page shows them and offers a
    review only when there is at least one."""


def get_deps(request: Request) -> AppDeps:
    return cast(AppDeps, request.app.state.deps)


def get_runner(request: Request) -> ReviewRunner:
    return cast(ReviewRunner, request.app.state.runner)


def get_shutdown(request: Request) -> asyncio.Event:
    """Set when the app's lifespan begins its teardown."""
    return cast(asyncio.Event, request.app.state.shutdown)


Deps = Annotated[AppDeps, Depends(get_deps)]
Runner = Annotated[ReviewRunner, Depends(get_runner)]
Shutdown = Annotated[asyncio.Event, Depends(get_shutdown)]
