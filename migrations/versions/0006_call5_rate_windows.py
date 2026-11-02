"""Call 5: per-account purchase request counter (purchase-015).

Revision ID: 0006_call5_rate_windows
Revises: 0005_schema_seams
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_call5_rate_windows"
down_revision = "0005_schema_seams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_rate_windows",
        sa.Column(
            "buyer_id",
            sa.BigInteger(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("request_count >= 0", name="ck_purchase_rate_windows_count"),
    )
    op.execute(
        """
        COMMENT ON TABLE purchase_rate_windows IS
        '[TEMPORARY_MVP_DEFAULT] Call 5 / purchase-015: fixed-window purchase request counter, one row per account (10 requests per 60 seconds).'
        """
    )


def downgrade() -> None:
    op.drop_table("purchase_rate_windows")
