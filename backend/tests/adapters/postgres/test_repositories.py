import asyncio
import itertools
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hfm.adapters.postgres.repositories import (
    PostgresMerchantMemory,
    PostgresReviewEventStore,
    PostgresReviewRepository,
)
from hfm.domain.events import ReviewEvent
from hfm.domain.models import Review, ReviewStatus
from hfm.platform.db import build_engine, session_factory


@pytest.fixture
async def sessions(pg_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = build_engine(pg_url)
    yield session_factory(engine)
    await engine.dispose()


# The module's tests share one database, where a month holds one standing review, so each review
# takes a month of its own.
_months = (f"{year}-09" for year in itertools.count(2000))


def make_review(review_id: str) -> Review:
    return Review(
        id=review_id,
        month=next(_months),
        status=ReviewStatus.RUNNING,
        created_at=datetime(2026, 10, 1, 8, 30, tzinfo=UTC),
    )


async def test_review_round_trip_and_status_change(sessions) -> None:
    repo = PostgresReviewRepository(sessions)
    review = make_review("r-round-trip")
    await repo.add(review)
    assert await repo.get("r-round-trip") == review
    await repo.set_status("r-round-trip", ReviewStatus.COMPLETED)
    assert (await repo.get("r-round-trip")).status is ReviewStatus.COMPLETED


async def test_unknown_review_raises_key_error(sessions) -> None:
    repo = PostgresReviewRepository(sessions)
    with pytest.raises(KeyError):
        await repo.get("missing")
    with pytest.raises(KeyError):
        await repo.set_status("missing", ReviewStatus.FAILED)
    with pytest.raises(KeyError):
        await repo.clear("missing", datetime.now(UTC))


async def test_duplicate_add_raises_and_keeps_original(sessions) -> None:
    repo = PostgresReviewRepository(sessions)
    await repo.add(make_review("r-dup"))
    with pytest.raises(ValueError, match="r-dup"):
        await repo.add(make_review("r-dup"))


async def test_events_get_sequential_numbers_and_list_after_seq(sessions) -> None:
    await PostgresReviewRepository(sessions).add(make_review("r-events"))
    store = PostgresReviewEventStore(sessions)
    seqs = [await store.append("r-events", ReviewEvent("t", {"n": n})) for n in (1, 2, 3)]
    assert seqs == [1, 2, 3]
    assert await store.list("r-events", after_seq=1) == [
        (2, ReviewEvent("t", {"n": 2})),
        (3, ReviewEvent("t", {"n": 3})),
    ]
    assert len(await store.list("r-events")) == 3


async def test_concurrent_appends_to_one_review_never_collide(sessions) -> None:
    await PostgresReviewRepository(sessions).add(make_review("r-concurrent"))
    store = PostgresReviewEventStore(sessions)
    seqs = await asyncio.gather(
        *(store.append("r-concurrent", ReviewEvent("t", {"n": n})) for n in range(8))
    )
    assert sorted(seqs) == list(range(1, 9))


async def test_append_to_unknown_review_raises_key_error(sessions) -> None:
    with pytest.raises(KeyError):
        await PostgresReviewEventStore(sessions).append("nope", ReviewEvent("t", {}))


async def test_merchant_memory_lookup_and_upsert(sessions) -> None:
    memory = PostgresMerchantMemory(sessions)
    await memory.remember("m-shufersal", "groceries")
    await memory.remember("m-shufersal", "household")
    await memory.remember("m-aroma", "dining")
    assert await memory.lookup(["m-shufersal", "m-aroma", "m-unknown"]) == {
        "m-shufersal": "household",
        "m-aroma": "dining",
    }


async def test_list_by_status_returns_matching_reviews_oldest_first(sessions) -> None:
    repo = PostgresReviewRepository(sessions)
    older, newer = make_review("r-list-older"), make_review("r-list-newer")
    await repo.add(replace(newer, created_at=newer.created_at + timedelta(minutes=5)))
    await repo.add(older)
    await repo.add(replace(make_review("r-list-done"), status=ReviewStatus.COMPLETED))

    running = [r.id for r in await repo.list_by_status(ReviewStatus.RUNNING)]

    assert [i for i in running if i.startswith("r-list-")] == ["r-list-older", "r-list-newer"]


async def test_a_month_holds_one_standing_review_until_it_is_cleared(sessions) -> None:
    repo = PostgresReviewRepository(sessions)
    first = make_review("r-standing-first")
    await repo.add(first)
    assert await repo.standing_for_month(first.month) == first
    with pytest.raises(ValueError, match=first.month):
        await repo.add(replace(make_review("r-standing-rival"), month=first.month))

    cleared_at = datetime(2026, 10, 2, tzinfo=UTC)
    await repo.clear(first.id, cleared_at)
    assert (await repo.get(first.id)).cleared_at == cleared_at
    assert await repo.standing_for_month(first.month) is None
    second = replace(make_review("r-standing-second"), month=first.month)
    await repo.add(second)
    assert await repo.standing_for_month(first.month) == second


async def test_list_created_since_includes_cleared_reviews_oldest_first(sessions) -> None:
    repo = PostgresReviewRepository(sessions)
    since = datetime(2031, 1, 1, tzinfo=UTC)
    before, older, newer = (make_review(f"r-since-{n}") for n in ("before", "older", "newer"))
    await repo.add(replace(before, created_at=since - timedelta(seconds=1)))
    await repo.add(replace(newer, created_at=since + timedelta(hours=2)))
    await repo.add(replace(older, created_at=since))
    await repo.clear(older.id, since + timedelta(hours=1))

    assert [r.id for r in await repo.list_created_since(since)] == [older.id, newer.id]
