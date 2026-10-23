"""The migration run alone prepares every table the app needs, the checkpointer's included."""

from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres.base import MIGRATIONS
from psycopg import AsyncConnection

from hfm.platform.checkpointer import libpq_dsn, open_checkpointer


async def _scalar(pg_url: str, sql: str) -> object:
    async with await AsyncConnection.connect(libpq_dsn(pg_url)) as conn:
        row = await (await conn.execute(sql)).fetchone()
    assert row is not None
    return row[0]


async def test_migration_run_creates_the_checkpoint_tables_at_their_latest_version(
    pg_url: str,
) -> None:
    version = await _scalar(pg_url, "SELECT max(v) FROM checkpoint_migrations")
    assert version == len(MIGRATIONS) - 1


async def test_opening_the_checkpointer_leaves_table_setup_to_the_migration_run(
    pg_url: str,
) -> None:
    async with await AsyncConnection.connect(libpq_dsn(pg_url), autocommit=True) as conn:
        await conn.execute("DROP TABLE IF EXISTS checkpoint_migrations")
    config = {"configurable": {"thread_id": "t-no-setup", "checkpoint_ns": ""}}
    async with open_checkpointer(libpq_dsn(pg_url)) as saver:
        await saver.aput(
            config, empty_checkpoint(), {"source": "input", "step": 0, "parents": {}}, {}
        )
    assert await _scalar(pg_url, "SELECT to_regclass('checkpoint_migrations')") is None
