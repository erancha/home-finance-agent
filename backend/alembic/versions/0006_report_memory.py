"""remember the report each of a person's recent review prompts got, so an identical review asks
no model

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_memory",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("prompt_digest", sa.Text(), nullable=False),
        sa.Column("month", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "written_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "prompt_digest"),
    )


def downgrade() -> None:
    op.drop_table("report_memory")
