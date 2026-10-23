"""Opens the Postgres-backed LangGraph checkpointer with the review's serializer, and brings its
tables to the installed library's version."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection, Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from hfm.application.review_graph import checkpoint_serde

_DRIVER_SUFFIX = "+psycopg"


def libpq_dsn(database_url: str) -> str:
    """Drop the SQLAlchemy driver suffix so libpq-style clients accept the URL."""
    return database_url.replace(_DRIVER_SUFFIX, "", 1)


def setup_checkpoint_tables(dsn: str) -> None:
    """Create the saver's tables or bring them to the installed library's version.

    Belongs to the one process that owns the schema, so replicas booting together never race on
    a create. The saver's setup is version-tracked and idempotent, so a library upgrade that adds
    a migration is applied by the next run with no Alembic revision. Autocommit because the
    saver's index migrations run CONCURRENTLY, which Postgres refuses inside a transaction.
    """
    with Connection.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        PostgresSaver(conn).setup()


@asynccontextmanager
async def open_checkpointer(dsn: str) -> AsyncIterator[AsyncPostgresSaver]:
    """Connections come from a pool that pings each one before handing it out, so a connection
    the database dropped (a restart, a failover) is replaced on the next checkout. The connection
    settings are the ones the saver's own from_conn_string applies, so the pool stands in for it.
    The tables are expected to exist already, from setup_checkpoint_tables.
    """
    # One warm connection covers the usual lone review; a few more let concurrent reviews
    # checkpoint without queuing behind each other.
    pool = AsyncConnectionPool(
        dsn,
        connection_class=AsyncConnection[DictRow],
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        min_size=1,
        max_size=4,
        check=AsyncConnectionPool.check_connection,
        open=False,
    )
    async with pool:
        yield AsyncPostgresSaver(conn=pool, serde=checkpoint_serde())
