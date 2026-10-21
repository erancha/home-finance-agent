"""Tables of the review store: reviews, their per-review event log and the merchant memory.

Reviews and remembered merchants carry the Google account id of the person they belong to."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ReviewRow(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        Index(
            "reviews_one_standing_per_month",
            "user_id",
            "month",
            unique=True,
            postgresql_where="cleared_at IS NULL",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text)
    month: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewEventRow(Base):
    __tablename__ = "review_events"

    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MerchantMemoryRow(Base):
    __tablename__ = "merchant_memory"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    merchant_key: Mapped[str] = mapped_column(Text, primary_key=True)
    category: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
