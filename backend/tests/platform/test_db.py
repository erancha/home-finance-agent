from sqlalchemy import text

from hfm.platform.db import build_engine, session_factory
from tests.platform.database_outage import sever_every_other_connection


async def test_sessions_survive_a_database_restart(pg_url: str) -> None:
    engine = build_engine(pg_url)
    sessions = session_factory(engine)
    try:
        async with sessions() as session:
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
        await sever_every_other_connection(pg_url)
        async with sessions() as session:
            assert (await session.execute(text("SELECT 2"))).scalar_one() == 2
    finally:
        await engine.dispose()
