"""SSE tests run the app under a real uvicorn server: TestClient buffers a response until the
app returns, and an event stream only returns when its client disconnects."""
import asyncio
import json
import signal
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from hfm.application.event_sink import ReviewEventSink
from hfm.domain.events import (
    AGENT_DISCOVERED,
    REVIEW_QUESTION,
    REVIEW_REPORT,
    REVIEW_TOTALS,
    ReviewEvent,
)
from hfm.platform.api.events import review_frames, sse_frame
from hfm.platform.app import SHUTDOWN_SIGNALS, create_app, signal_shutdown
from tests.fakes import InMemoryEventBus, InMemoryReviewEventStore
from tests.platform.support import (
    CATEGORY_QUESTION,
    EVENT_TIME,
    MONTH,
    UNKNOWN_MERCHANT,
    app_deps,
    scripted,
)

DEADLINE_SECONDS = 5.0


@contextmanager
def serve(app: FastAPI) -> Iterator[httpx.Client]:
    """Yield a client of the app served on a free local port; the server stops on exit."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, timeout_graceful_shutdown=2))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + DEADLINE_SECONDS
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.01)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=DEADLINE_SECONDS) as client:
            yield client
    finally:
        server.should_exit = True
        thread.join(DEADLINE_SECONDS)
        assert not thread.is_alive(), "uvicorn did not stop"


def frames(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    """Parse SSE frames; comment lines such as keepalives are skipped."""
    fields: dict[str, str] = {}
    for line in lines:
        if line.startswith(":"):
            continue
        if line:
            name, _, value = line.partition(": ")
            fields[name] = value
            continue
        if fields:
            yield {"seq": int(fields["id"]), "type": fields["event"],
                   "data": json.loads(fields["data"])}
            fields = {}


def until(stream: Iterator[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    read: list[dict[str, Any]] = []
    for frame in stream:
        read.append(frame)
        if frame["type"] == event_type:
            return read
    raise AssertionError(f"stream ended before {event_type}")


def wait_for_status(client: httpx.Client, review_id: str, expected: str) -> None:
    deadline = time.monotonic() + DEADLINE_SECONDS
    while (status := client.get(f"/api/reviews/{review_id}").json()["status"]) != expected:
        assert time.monotonic() < deadline, f"review stayed {status}"
        time.sleep(0.01)


def test_sse_frame_renders_id_event_and_one_line_of_json() -> None:
    frame = sse_frame(3, "agent.status", {"text": "שלום\nworld"})
    assert frame == 'id: 3\nevent: agent.status\ndata: {"text": "שלום\\nworld"}\n\n'


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


class RacingStore(InMemoryReviewEventStore):
    """Emits one event just before the replay snapshot is taken and one just after it."""

    def __init__(self) -> None:
        super().__init__()
        self.sink = ReviewEventSink(self, bus := InMemoryEventBus(), lambda: EVENT_TIME)
        self.bus = bus

    async def list(self, review_id: str, after_seq: int = 0) -> list[tuple[int, ReviewEvent]]:
        await self.sink.emit(review_id, ReviewEvent("before.snapshot", {}))
        snapshot = await super().list(review_id, after_seq)
        await self.sink.emit(review_id, ReviewEvent("after.snapshot", {}))
        return snapshot


async def test_events_racing_the_replay_arrive_once_each() -> None:
    store = RacingStore()
    await store.append("r1", ReviewEvent("persisted", {}))
    stream = review_frames(
        ConnectedRequest(), store, store.bus, "r1", 0, asyncio.Event()  # type: ignore[arg-type]
    )

    sent = [await anext(stream) for _ in range(3)]
    await stream.aclose()

    assert sent == [
        sse_frame(1, "persisted", {}),
        sse_frame(2, "before.snapshot", {"at": EVENT_TIME.isoformat()}),
        sse_frame(3, "after.snapshot", {"at": EVENT_TIME.isoformat()}),
    ]
    assert store.bus.subscriber_count("review:r1") == 0


async def test_stream_ends_soon_after_shutdown_is_signalled() -> None:
    store = InMemoryReviewEventStore()
    await store.append("r1", ReviewEvent("persisted", {}))
    shutdown = asyncio.Event()
    stream = review_frames(
        ConnectedRequest(), store, InMemoryEventBus(), "r1", 0, shutdown  # type: ignore[arg-type]
    )
    assert await anext(stream) == sse_frame(1, "persisted", {})

    pending = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0.05)
    assert not pending.done()
    shutdown.set()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(pending, timeout=1)


@contextmanager
def sigterm_ignored() -> Iterator[None]:
    """Uvicorn re-raises the signal it shut down on; ignoring it keeps pytest alive."""
    previous = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


async def test_sigterm_ends_open_streams_so_the_lifespan_teardown_runs() -> None:
    """Uvicorn runs on this (main) thread so it installs its signal handlers, as in production."""
    app = create_app(deps=app_deps(scripted(UNKNOWN_MERCHANT)))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_config=None))
    opened = threading.Event()

    def watch_stream() -> int:
        with httpx.Client(base_url=base, timeout=DEADLINE_SECONDS) as client:
            review_id = client.post("/api/reviews", json={"month": MONTH}).json()["id"]
            with client.stream("GET", f"/api/reviews/{review_id}/events") as response:
                opened.set()
                return sum(1 for _ in frames(response.iter_lines()))

    with sigterm_ignored():
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started:
            await asyncio.sleep(0.01)
        watcher = asyncio.create_task(asyncio.to_thread(watch_stream))
        await asyncio.to_thread(opened.wait, DEADLINE_SECONDS)

        signal.raise_signal(signal.SIGTERM)
        await asyncio.wait_for(serving, timeout=DEADLINE_SECONDS)
        assert await asyncio.wait_for(watcher, timeout=DEADLINE_SECONDS) >= 1
    assert app.state.shutdown.is_set()


async def test_signal_shutdown_sets_the_event_and_chains_the_prior_handler() -> None:
    received: list[int] = []

    def prior(sig: int, frame: FrameType | None) -> None:
        received.append(sig)

    shutdown = asyncio.Event()
    previous = signal.signal(signal.SIGTERM, prior)
    try:
        with signal_shutdown(shutdown):
            signal.raise_signal(signal.SIGTERM)
            await asyncio.wait_for(shutdown.wait(), timeout=1)
        assert received == [signal.SIGTERM]
        assert signal.getsignal(signal.SIGTERM) is prior
    finally:
        signal.signal(signal.SIGTERM, previous)


async def test_signal_shutdown_restores_the_default_for_a_handler_python_cannot_see(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """getsignal answers None for a handler installed from C; restoring None would raise."""
    saved = {sig: signal.getsignal(sig) for sig in SHUTDOWN_SIGNALS}
    monkeypatch.setattr(signal, "getsignal", lambda sig: None)
    try:
        with signal_shutdown(asyncio.Event()):
            pass
        monkeypatch.undo()
        assert {sig: signal.getsignal(sig) for sig in SHUTDOWN_SIGNALS} == {
            sig: signal.SIG_DFL for sig in SHUTDOWN_SIGNALS
        }
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)


def test_events_replays_persisted_events_before_tailing() -> None:
    app = create_app(deps=app_deps(scripted(UNKNOWN_MERCHANT)))
    with serve(app) as client:
        review_id = client.post("/api/reviews", json={"month": MONTH}).json()["id"]
        wait_for_status(client, review_id, "waiting")

        with client.stream("GET", f"/api/reviews/{review_id}/events") as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            stream = frames(response.iter_lines())
            replayed = until(stream, REVIEW_QUESTION)
            answered = client.post(
                f"/api/reviews/{review_id}/answers",
                json={"answers": {CATEGORY_QUESTION: "dining"}},
            )
            assert answered.status_code == 204
            tailed = until(stream, REVIEW_REPORT)

        assert replayed[0]["type"] == AGENT_DISCOVERED
        seqs = [frame["seq"] for frame in replayed + tailed]
        assert seqs == list(range(1, len(seqs) + 1))
        assert [frame["type"] for frame in tailed] == [REVIEW_TOTALS, REVIEW_REPORT]

        last_question = replayed[-1]["seq"]
        with client.stream(
            "GET",
            f"/api/reviews/{review_id}/events",
            headers={"Last-Event-ID": str(last_question)},
        ) as response:
            resumed = until(frames(response.iter_lines()), REVIEW_REPORT)
        assert [frame["seq"] for frame in resumed] == [last_question + 1, last_question + 2]
