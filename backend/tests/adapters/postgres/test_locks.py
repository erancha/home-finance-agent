import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hfm.adapters.postgres.locks import PostgresLocks
from hfm.platform.db import build_engine, session_factory
from hfm.ports import Locks
from tests.platform.database_outage import sever_every_other_connection


@pytest.fixture
async def sessions(pg_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = build_engine(pg_url)
    yield session_factory(engine)
    await engine.dispose()


def test_postgres_locks_satisfy_the_port(sessions) -> None:
    assert isinstance(PostgresLocks(sessions), Locks)


async def test_a_held_lock_is_refused_to_another_holder_until_released(sessions) -> None:
    locks = PostgresLocks(sessions)
    async with locks.try_hold("review:r1") as held:
        assert held
        async with locks.try_hold("review:r1") as again:
            assert not again
        async with locks.try_hold("review:r2") as other:
            assert other
    async with locks.try_hold("review:r1") as after:
        assert after


async def test_a_lock_is_released_when_its_holders_connection_dies(pg_url: str, sessions) -> None:
    locks = PostgresLocks(sessions)
    holder = locks.try_hold("review:r-dead")
    assert await holder.__aenter__()

    await sever_every_other_connection(pg_url)

    async with locks.try_hold("review:r-dead") as held:
        assert held
    with pytest.raises(DBAPIError):
        await holder.__aexit__(None, None, None)


async def test_hold_waits_until_the_holder_releases(sessions) -> None:
    locks = PostgresLocks(sessions)
    order: list[str] = []

    async def second() -> None:
        async with locks.hold("starts:1001"):
            order.append("second")

    async with locks.hold("starts:1001"):
        waiter = asyncio.create_task(second())
        await asyncio.sleep(0.2)
        order.append("first")
    await waiter

    assert order == ["first", "second"]
