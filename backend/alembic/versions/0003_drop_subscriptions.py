"""forget merchants remembered under the dropped subscriptions category

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # "subscriptions" named how a charge is paid, so it maps onto no single category; a forgotten
    # merchant takes the card agent's category again, or is asked about once.
    op.execute("DELETE FROM merchant_memory WHERE category = 'subscriptions'")


def downgrade() -> None:
    raise NotImplementedError("forgotten merchants cannot be restored")
