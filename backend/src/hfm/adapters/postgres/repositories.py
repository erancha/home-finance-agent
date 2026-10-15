"""Postgres implementations of the persistence ports.

Core building blocks:
- PostgresReviewRepository: review rows; a unique index keeps one review per month uncleared
- PostgresReviewEventStore: per-review event log, sequence assigned under a review row lock
- PostgresMerchantMemory: merchant key to category upserts

Each call runs in its own session; a write commits before the call returns.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hfm.adapters.postgres.orm import MerchantMemoryRow, ReviewEventRow, ReviewRow
from hfm.domain.events import ReviewEvent
from hfm.domain.models import Review, ReviewStatus

UNIQUE_VIOLATION = "23505"


class PostgresReviewRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, review: Review) -> None:
        try:
            async with self._sessions.begin() as session:
                session.add(
                    ReviewRow(
                        id=review.id,
                        month=review.month,
                        status=review.status.value,
                        created_at=review.created_at,
                        cleared_at=review.cleared_at,
                    )
                )
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == UNIQUE_VIOLATION:
                raise ValueError(
                    f"review {review.id} or a standing review of {review.month} already exists"
                ) from error
            raise

    async def get(self, review_id: str) -> Review:
        async with self._sessions() as session:
            row = await session.get(ReviewRow, review_id)
        if row is None:
            raise KeyError(review_id)
        return _review(row)

    async def set_status(self, review_id: str, status: ReviewStatus) -> None:
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(ReviewRow).where(ReviewRow.id == review_id).values(status=status.value)
            )
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise KeyError(review_id)

    async def list_by_status(self, status: ReviewStatus) -> list[Review]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(ReviewRow)
                .where(ReviewRow.status == status.value)
                .order_by(ReviewRow.created_at)
            )
            return [_review(row) for row in rows]

    async def standing_for_month(self, month: str) -> Review | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(ReviewRow).where(ReviewRow.month == month, ReviewRow.cleared_at.is_(None))
            )
        return None if row is None else _review(row)

    async def list_created_since(self, since: datetime) -> list[Review]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(ReviewRow)
                .where(ReviewRow.created_at >= since)
                .order_by(ReviewRow.created_at)
            )
            return [_review(row) for row in rows]

    async def clear(self, review_id: str, at: datetime) -> None:
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(ReviewRow).where(ReviewRow.id == review_id).values(cleared_at=at)
            )
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise KeyError(review_id)


def _review(row: ReviewRow) -> Review:
    return Review(
        id=row.id,
        month=row.month,
        status=ReviewStatus(row.status),
        created_at=row.created_at,
        cleared_at=row.cleared_at,
    )


class PostgresReviewEventStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append(self, review_id: str, event: ReviewEvent) -> int:
        async with self._sessions.begin() as session:
            locked = await session.execute(
                select(ReviewRow.id).where(ReviewRow.id == review_id).with_for_update()
            )
            if locked.scalar_one_or_none() is None:
                raise KeyError(review_id)
            last: int | None = await session.scalar(
                select(func.coalesce(func.max(ReviewEventRow.seq), 0)).where(
                    ReviewEventRow.review_id == review_id
                )
            )
            assert last is not None, "coalesce(max(seq), 0) always yields a row"
            seq = last + 1
            session.add(
                ReviewEventRow(review_id=review_id, seq=seq, type=event.type, data=event.data)
            )
        return seq

    async def list(self, review_id: str, after_seq: int = 0) -> list[tuple[int, ReviewEvent]]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(ReviewEventRow)
                .where(ReviewEventRow.review_id == review_id, ReviewEventRow.seq > after_seq)
                .order_by(ReviewEventRow.seq)
            )
            return [(row.seq, ReviewEvent(type=row.type, data=row.data)) for row in rows]


class PostgresMerchantMemory:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def lookup(self, keys: Iterable[str]) -> dict[str, str]:
        async with self._sessions() as session:
            rows = await session.execute(
                select(MerchantMemoryRow.merchant_key, MerchantMemoryRow.category).where(
                    MerchantMemoryRow.merchant_key.in_(list(keys))
                )
            )
            return {key: category for key, category in rows}

    async def remember(self, key: str, category: str) -> None:
        statement = insert(MerchantMemoryRow).values(merchant_key=key, category=category)
        statement = statement.on_conflict_do_update(
            index_elements=[MerchantMemoryRow.merchant_key],
            set_={"category": category, "updated_at": func.now()},
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)
