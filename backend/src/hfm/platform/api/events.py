"""Server-sent event stream of one review: its persisted history, then live events.

The stream subscribes to the review's bus channel before reading the log, so an event emitted
between the two arrives on the queue; queued events the replay already sent are skipped by
sequence number. The log assigns sequences in commit order without gaps, so a replay holds every
sequence up to its last. A reconnecting browser sends Last-Event-ID and gets only what follows it.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from hfm.application.event_sink import review_channel
from hfm.platform.dependencies import Deps, Runner, Shutdown
from hfm.ports import EventBus, ReviewEventStore

KEEPALIVE_SECONDS = 15.0
KEEPALIVE_FRAME = ": keepalive\n\n"

router = APIRouter()


def sse_frame(seq: int, event_type: str, data: dict[str, Any]) -> str:
    return f"id: {seq}\nevent: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def review_frames(
    request: Request,
    store: ReviewEventStore,
    bus: EventBus,
    review_id: str,
    after_seq: int,
    shutdown: asyncio.Event,
) -> AsyncIterator[str]:
    """Runs until the client disconnects or the app shuts down; terminal review events do not
    end the stream."""
    async with bus.subscribe(review_channel(review_id)) as queue:
        replayed_through = after_seq
        for seq, event in await store.list(review_id, after_seq):
            yield sse_frame(seq, event.type, event.data)
            replayed_through = seq
        stopping = asyncio.ensure_future(shutdown.wait())
        receiving: asyncio.Future[dict[str, Any]] | None = None
        try:
            while not await request.is_disconnected():
                if receiving is None:
                    receiving = asyncio.ensure_future(queue.get())
                waiting: set[asyncio.Future[Any]] = {receiving, stopping}
                done, _ = await asyncio.wait(
                    waiting,
                    timeout=KEEPALIVE_SECONDS,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if stopping in done:
                    return
                if receiving not in done:
                    yield KEEPALIVE_FRAME
                    continue
                live, receiving = receiving.result(), None
                # Parallel nodes may publish out of sequence order, so compare against the replay
                # snapshot rather than the latest frame sent.
                if live["seq"] > replayed_through:
                    yield sse_frame(live["seq"], live["type"], live["data"])
        finally:
            stopping.cancel()
            if receiving is not None:
                receiving.cancel()


@router.get("/api/reviews/{review_id}/events")
async def review_events(
    review_id: str,
    request: Request,
    runner: Runner,
    deps: Deps,
    shutdown: Shutdown,
    last_event_id: Annotated[int | None, Header()] = None,
) -> StreamingResponse:
    """Last-Event-ID is absent on a first connection, which replays the whole log."""
    await runner.review(review_id)
    after_seq = 0 if last_event_id is None else last_event_id
    return StreamingResponse(
        review_frames(request, deps.events, deps.bus, review_id, after_seq, shutdown),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
