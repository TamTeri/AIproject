"""Create temporary hold, order, and purchase-attempt persistence seams.

Revision ID: 0004_purchase_audit
Revises: 0003_accounts_catalog
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_purchase_audit"
down_revision = "0003_accounts_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holds",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "buyer_id",
            sa.BigInteger(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quote_snapshot", postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint("id", "buyer_id", "event_id", name="uq_holds_identity_tuple"),
        sa.CheckConstraint("quantity > 0", name="ck_holds_quantity_positive"),
        sa.CheckConstraint(
            "status IN ('active', 'converted', 'cancelled', 'expired', 'payment_failed')",
            name="ck_holds_status",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_holds_expiry_after_creation"),
        sa.CheckConstraint(
            "(status = 'active' AND terminal_at IS NULL) OR (status <> 'active' AND terminal_at IS NOT NULL)",
            name="ck_holds_terminal_state",
        ),
    )
    op.create_index("ix_holds_event_status_expiry", "holds", ["event_id", "status", "expires_at"])
    op.create_index("ix_holds_buyer_status", "holds", ["buyer_id", "status"])

    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("buyer_id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("hold_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "currency_code",
            sa.String(length=3),
            sa.ForeignKey("currencies.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rate_applied", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("discount_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("quote_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["hold_id", "buyer_id", "event_id"],
            ["holds.id", "holds.buyer_id", "holds.event_id"],
            name="fk_orders_hold_owner_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["buyer_id"],
            ["accounts.id"],
            name="fk_orders_buyer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="fk_orders_event",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        sa.CheckConstraint("rate_applied > 0", name="ck_orders_rate_positive"),
        sa.CheckConstraint("discount_minor >= 0", name="ck_orders_discount_nonnegative"),
        sa.CheckConstraint("total_minor >= 0", name="ck_orders_total_nonnegative"),
    )
    op.create_index("ix_orders_buyer_created_at", "orders", ["buyer_id", "created_at"])
    op.create_index("ix_orders_event", "orders", ["event_id"])

    op.create_table(
        "purchase_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("buyer_id", sa.BigInteger(), nullable=True),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("quantity_raw", sa.Integer(), nullable=True),
        sa.Column("currency_raw", sa.String(length=16), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("hold_id", sa.BigInteger(), nullable=True),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["buyer_id"], ["accounts.id"], name="fk_purchase_attempts_buyer", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name="fk_purchase_attempts_event", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["hold_id"], ["holds.id"], name="fk_purchase_attempts_hold", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name="fk_purchase_attempts_order", ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "quantity_raw IS NULL OR quantity_raw BETWEEN -1000000 AND 1000000",
            name="ck_purchase_attempts_quantity_bound",
        ),
        sa.CheckConstraint(
            "currency_raw IS NULL OR char_length(currency_raw) BETWEEN 1 AND 16",
            name="ck_purchase_attempts_currency_bound",
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'rejected', 'failed', 'replayed')",
            name="ck_purchase_attempts_outcome",
        ),
        sa.CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 64",
            name="ck_purchase_attempts_reason_code",
        ),
        sa.CheckConstraint(
            "request_id IS NULL OR char_length(request_id) BETWEEN 1 AND 128",
            name="ck_purchase_attempts_request_id_bound",
        ),
        sa.CheckConstraint(
            "idempotency_key IS NULL OR char_length(idempotency_key) BETWEEN 1 AND 128",
            name="ck_purchase_attempts_idempotency_key_bound",
        ),
    )
    op.create_index("ix_purchase_attempts_submitted_at", "purchase_attempts", ["submitted_at"])
    op.create_index(
        "ix_purchase_attempts_buyer_submitted_at", "purchase_attempts", ["buyer_id", "submitted_at"]
    )
    op.create_index("ix_purchase_attempts_outcome", "purchase_attempts", ["outcome"])


def downgrade() -> None:
    op.drop_index("ix_purchase_attempts_outcome", table_name="purchase_attempts")
    op.drop_index("ix_purchase_attempts_buyer_submitted_at", table_name="purchase_attempts")
    op.drop_index("ix_purchase_attempts_submitted_at", table_name="purchase_attempts")
    op.drop_table("purchase_attempts")
    op.drop_index("ix_orders_event", table_name="orders")
    op.drop_index("ix_orders_buyer_created_at", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_holds_buyer_status", table_name="holds")
    op.drop_index("ix_holds_event_status_expiry", table_name="holds")
    op.drop_table("holds")
