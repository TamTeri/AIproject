"""Call 6: exchange-rate change history (admin-006).

Revision ID: 0007_rate_history
Revises: 0006_call5_rate_windows
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_rate_history"
down_revision = "0006_call5_rate_windows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchange_rate_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("currency", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("old_rate", sa.Numeric(18, 8), nullable=True),
        sa.Column("new_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("changed_by", sa.BigInteger(), sa.ForeignKey("accounts.id", ondelete="SET NULL")),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.CheckConstraint("new_rate > 0", name="ck_exchange_rate_history_positive"),
    )
    op.create_index("ix_exchange_rate_history_currency", "exchange_rate_history", ["currency", "changed_at"])


def downgrade() -> None:
    op.drop_index("ix_exchange_rate_history_currency", table_name="exchange_rate_history")
    op.drop_table("exchange_rate_history")
