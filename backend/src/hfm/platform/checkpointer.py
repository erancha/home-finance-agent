"""Opens the Postgres-backed LangGraph checkpointer with the review's serializer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from hfm.application.review_graph import checkpoint_serde

_DRIVER_SUFFIX = "+psycopg"


def libpq_dsn(database_url: str) -> str:
    """Drop the SQLAlchemy driver suffix so libpq-style clients accept the URL."""
    return database_url.replace(_DRIVER_SUFFIX, "", 1)


@asynccontextmanager
async def open_checkpointer(dsn: str) -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(dsn, serde=checkpoint_serde()) as saver:
        await saver.setup()
        yield saver
