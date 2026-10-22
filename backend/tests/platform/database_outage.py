"""Simulates a database restart as the agent's connections see it: every server session dies."""

from __future__ import annotations

import psycopg

from hfm.platform.checkpointer import libpq_dsn


async def sever_every_other_connection(pg_url: str) -> None:
    """Terminate every server session but this one, as a Postgres restart would."""
    async with await psycopg.AsyncConnection.connect(libpq_dsn(pg_url), autocommit=True) as conn:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE pid <> pg_backend_pid() AND datname = current_database()"
        )
