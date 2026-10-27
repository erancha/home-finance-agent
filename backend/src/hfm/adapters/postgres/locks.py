"""Postgres implementation of the Locks port, on advisory locks.

Each held lock is a transaction-scoped advisory lock inside a transaction of its own, kept open
for the context, so the lock is released with that transaction: when the context exits, or when
Postgres ends the holder's session because its process died. Keys are hashed to the 64-bit
numbers advisory locks take; two keys sharing a hash would share a lock, which only makes a holder
wait or refuse needlessly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_HOLD = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")
_TRY_HOLD = text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))")


class PostgresLocks:
    """Each held lock occupies one pooled connection for as long as it is held."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        async with self._sessions.begin() as session:
            await session.execute(_HOLD, {"key": key})
            yield

    @asynccontextmanager
    async def try_hold(self, key: str) -> AsyncIterator[bool]:
        async with self._sessions.begin() as session:
            held: bool | None = await session.scalar(_TRY_HOLD, {"key": key})
            assert held is not None, "pg_try_advisory_xact_lock always returns a boolean"
            yield held
