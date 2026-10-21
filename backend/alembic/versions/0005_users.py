"""every review and remembered merchant belongs to a user

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("reviews", "merchant_memory"):
        op.add_column(table, sa.Column("user_id", sa.Text(), nullable=False))
    op.drop_index("reviews_one_standing_per_month", table_name="reviews")
    op.create_index(
        "reviews_one_standing_per_month",
        "reviews",
        ["user_id", "month"],
        unique=True,
        postgresql_where=sa.text("cleared_at IS NULL"),
    )
    op.drop_constraint("merchant_memory_pkey", "merchant_memory", type_="primary")
    op.create_primary_key("merchant_memory_pkey", "merchant_memory", ["user_id", "merchant_key"])


def downgrade() -> None:
    op.drop_constraint("merchant_memory_pkey", "merchant_memory", type_="primary")
    op.execute(
        "DELETE FROM merchant_memory a USING merchant_memory b"
        " WHERE a.merchant_key = b.merchant_key AND a.updated_at < b.updated_at"
    )
    op.create_primary_key("merchant_memory_pkey", "merchant_memory", ["merchant_key"])
    op.drop_index("reviews_one_standing_per_month", table_name="reviews")
    op.execute(
        "UPDATE reviews SET cleared_at = now() WHERE cleared_at IS NULL AND id NOT IN ("
        " SELECT DISTINCT ON (month) id FROM reviews WHERE cleared_at IS NULL"
        " ORDER BY month, created_at DESC)"
    )
    op.create_index(
        "reviews_one_standing_per_month",
        "reviews",
        ["month"],
        unique=True,
        postgresql_where=sa.text("cleared_at IS NULL"),
    )
    op.drop_column("merchant_memory", "user_id")
    op.drop_column("reviews", "user_id")
