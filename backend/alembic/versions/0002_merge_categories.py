"""merge remembered categories into the shorter category list

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Key: a category dropped from the list. Value: the category that absorbs it.
MERGED = {
    "fuel": "transport",
    "clothing": "shopping",
    "electronics": "shopping",
    "kids": "education",
    "fees": "other",
    "transfers": "other",
}


def upgrade() -> None:
    for old, new in MERGED.items():
        op.execute(
            f"UPDATE merchant_memory SET category = '{new}', updated_at = now() "
            f"WHERE category = '{old}'"
        )


def downgrade() -> None:
    raise NotImplementedError("merged categories cannot be split again")
