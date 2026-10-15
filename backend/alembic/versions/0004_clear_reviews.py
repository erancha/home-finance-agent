"""one standing review per month; older reviews of a month are cleared

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True))
    # Each month keeps its newest review standing, so the person reopens what they saw last.
    op.execute(
        "UPDATE reviews SET cleared_at = now() WHERE id IN ("
        " SELECT id FROM (SELECT id, row_number() OVER"
        " (PARTITION BY month ORDER BY created_at DESC) AS age FROM reviews) ranked"
        " WHERE age > 1)"
    )
    op.create_index(
        "reviews_one_standing_per_month",
        "reviews",
        ["month"],
        unique=True,
        postgresql_where=sa.text("cleared_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("reviews_one_standing_per_month", table_name="reviews")
    op.drop_column("reviews", "cleared_at")
