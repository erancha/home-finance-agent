"""The FastAPI application and the composition of its production dependencies.

Core building blocks:
- create_app: routes (sign-in, reviews, events, card agents), error mapping, probes and the
  optional static frontend; its lifespan builds the production wiring unless AppDeps are
  injected, then the ReviewRunner, which fails the reviews a stopped server left running before
  the app serves
- production_deps: database engine, repositories, Postgres checkpointer, card-agent client, the
  card-agent registry and the budget file, report writer, token verifier, event bus and the review
  graph, all closed in reverse order on shutdown
- open_event_bus: the in-process bus, or the Redis bus when REDIS_URL is set
- /health answers while the process runs; /ready also needs the database to answer SELECT 1
- signal_shutdown: tells open event streams to end when the server is asked to stop
"""
from __future__ import annotations

import asyncio
import signal
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import (
    AbstractAsyncContextManager,
    AsyncExitStack,
    asynccontextmanager,
    contextmanager,
    nullcontext,
)
from pathlib import Path
from types import FrameType
from typing import Any

import structlog
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import SecretStr
from sqlalchemy import text

from hfm.adapters.a2a_client import A2ACardAgentClient
from hfm.adapters.config_files import load_budget, load_card_agents
from hfm.adapters.google_tokens import GoogleTokenVerifier, JwksKeys, StaticKey
from hfm.adapters.memory_bus import InMemoryEventBus
from hfm.adapters.postgres.repositories import (
    PostgresMerchantMemory,
    PostgresReviewEventStore,
    PostgresReviewRepository,
)
from hfm.adapters.redis_bus import RedisEventBus
from hfm.adapters.report_writer import CannedReportWriter, build_report_writer
from hfm.application.event_sink import ReviewEventSink
from hfm.application.review_graph import GraphDeps, build_review_graph
from hfm.platform.api import agents, auth, events, reviews
from hfm.platform.checkpointer import libpq_dsn, open_checkpointer
from hfm.platform.config import Settings, get_settings
from hfm.platform.db import build_engine, session_factory
from hfm.platform.dependencies import AppDeps, Deps
from hfm.platform.logging import configure_logging
from hfm.platform.review_runner import ReviewRunner
from hfm.ports import EventBus

__all__ = ["AppDeps", "create_app", "production_deps"]

log = structlog.get_logger(__name__)


def token_verifier(settings: Settings) -> GoogleTokenVerifier:
    """Google's published keys, unless a public key file stands in for them (tests only)."""
    keys = (
        JwksKeys(settings.auth_jwks_url)
        if settings.auth_public_key_file is None
        else StaticKey.from_file(settings.auth_public_key_file)
    )
    return GoogleTokenVerifier(settings.google_client_id, settings.auth_issuer, keys)


@asynccontextmanager
async def open_event_bus(redis_url: SecretStr | None) -> AsyncIterator[EventBus]:
    """Live events cross processes through Redis when a URL is set; otherwise they stay in this
    process, which must then serve every request of a review it runs."""
    if redis_url is None:
        yield InMemoryEventBus()
        return
    bus = RedisEventBus(redis_url.get_secret_value())
    try:
        yield bus
    finally:
        await bus.aclose()


@asynccontextmanager
async def production_deps(settings: Settings) -> AsyncIterator[AppDeps]:
    """Config files load first, so a bad file fails startup before any connection opens."""
    card_agents = load_card_agents(settings.card_agents_file)
    budget = load_budget(settings.budget_config)
    verifier = token_verifier(settings)
    writer = (
        CannedReportWriter() if settings.hfm_e2e else build_report_writer(*settings.report_model())
    )
    database_url = settings.database_url.get_secret_value()
    async with AsyncExitStack() as stack:
        engine = build_engine(database_url)
        stack.push_async_callback(engine.dispose)
        sessions = session_factory(engine)
        checkpointer = await stack.enter_async_context(
            open_checkpointer(libpq_dsn(database_url))
        )
        card_client = A2ACardAgentClient()
        stack.push_async_callback(card_client.aclose)
        store = PostgresReviewEventStore(sessions)
        bus = await stack.enter_async_context(open_event_bus(settings.redis_url))
        sink = ReviewEventSink(store, bus)
        graph_deps = GraphDeps(
            card_client, PostgresMerchantMemory(sessions), budget, writer, sink, card_agents
        )
        yield AppDeps(
            reviews=PostgresReviewRepository(sessions),
            events=store,
            bus=bus,
            sink=sink,
            graph=build_review_graph(graph_deps, checkpointer),
            sessions=sessions,
            verifier=verifier,
            google_client_id=settings.google_client_id,
            card_agents=tuple(card_agents),
        )


SHUTDOWN_SIGNALS = (signal.SIGINT, signal.SIGTERM)


@contextmanager
def signal_shutdown(shutdown: asyncio.Event) -> Iterator[None]:
    """Set the shutdown event on SIGINT or SIGTERM, then hand the signal to the prior handler.

    Uvicorn waits for open responses to finish before it runs the lifespan teardown, so an event
    stream that only learnt of shutdown there would hold the server open forever. Python lets
    only the main thread install handlers; off it (TestClient runs the lifespan in a worker
    thread) the lifespan teardown is the only trigger.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    loop = asyncio.get_running_loop()
    prior = {sig: _restorable(signal.getsignal(sig)) for sig in SHUTDOWN_SIGNALS}

    def handle(sig: int, frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(shutdown.set)
        previous = prior[signal.Signals(sig)]
        if callable(previous):
            previous(sig, frame)
        else:
            signal.signal(sig, previous)
            signal.raise_signal(sig)

    for sig in SHUTDOWN_SIGNALS:
        signal.signal(sig, handle)
    try:
        yield
    finally:
        for sig, previous in prior.items():
            signal.signal(sig, previous)


def _restorable(
    handler: Callable[[int, FrameType | None], Any] | int | None,
) -> Callable[[int, FrameType | None], Any] | int:
    """getsignal answers None for a handler installed outside Python, which cannot be put back;
    the default action is the closest restorable handler."""
    return signal.SIG_DFL if handler is None else handler


def create_app(settings: Settings | None = None, deps: AppDeps | None = None) -> FastAPI:
    """Without deps the app is the production process: it configures logging and wires itself
    from settings, read from the environment when not given."""
    source: AbstractAsyncContextManager[AppDeps]
    if deps is None:
        configure_logging()
        if settings is None:
            settings = get_settings()
        source = production_deps(settings)
    else:
        source = nullcontext(deps)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with source as resolved:
            runner = ReviewRunner(resolved.graph, resolved.reviews, resolved.sink)
            await runner.fail_interrupted()
            shutdown = asyncio.Event()
            app.state.deps = resolved
            app.state.runner = runner
            app.state.shutdown = shutdown
            try:
                with signal_shutdown(shutdown):
                    yield
            finally:
                shutdown.set()
                await runner.aclose()

    app = FastAPI(title="Home finance agent", lifespan=lifespan)
    reviews.register_error_handlers(app)
    auth.register_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(reviews.router)
    app.include_router(reviews.months_router)
    app.include_router(events.router)
    app.include_router(agents.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(wired: Deps) -> JSONResponse:
        """Any failure of the probe query means not ready; the cause is logged."""
        try:
            async with wired.sessions() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            log.warning("readiness probe failed", exc_info=True)
            return JSONResponse(
                {"status": "not ready"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return JSONResponse({"status": "ok"})

    if settings is not None and settings.hfm_frontend_dist is not None:
        _mount_frontend(app, settings.hfm_frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Mounted last so the API routes take precedence over the catch-all static mount."""
    if not (dist / "index.html").is_file():
        raise FileNotFoundError(f"HFM_FRONTEND_DIST={dist} has no index.html; build the frontend")
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
