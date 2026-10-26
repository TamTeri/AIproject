"""Add temporary idempotency, derived availability, and audit append-only seams.

Revision ID: 0005_schema_seams
Revises: 0004_purchase_audit
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_schema_seams"
down_revision = "0004_purchase_audit"
branch_labels = None
depends_on = None


TEMPORARY_POLICY = "[TEMPORARY_MVP_DEFAULT]"


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("buyer_id", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="in_progress"),
        sa.Column("outcome_payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "policy_status",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'[TEMPORARY_MVP_DEFAULT]'"),
        ),
        sa.PrimaryKeyConstraint("buyer_id", "idempotency_key", name="pk_idempotency_records"),
        sa.ForeignKeyConstraint(
            ["buyer_id"],
            ["accounts.id"],
            name="fk_idempotency_records_buyer",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "char_length(idempotency_key) BETWEEN 1 AND 128",
            name="ck_idempotency_key_bound",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-fA-F]{64}$'",
            name="ck_idempotency_request_hash",
        ),
        sa.CheckConstraint(
            "state IN ('in_progress', 'completed', 'failed')",
            name="ck_idempotency_state",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_idempotency_expiry_after_creation"),
        sa.CheckConstraint(
            "(state = 'in_progress' AND completed_at IS NULL) OR "
            "(state IN ('completed', 'failed') AND completed_at IS NOT NULL)",
            name="ck_idempotency_completion_state",
        ),
        sa.CheckConstraint(
            "outcome_payload IS NULL OR octet_length(outcome_payload::text) <= 65536",
            name="ck_idempotency_payload_bound",
        ),
        sa.CheckConstraint(
            "policy_status = '[TEMPORARY_MVP_DEFAULT]'",
            name="ck_idempotency_temporary_policy",
        ),
    )
    op.create_index("ix_idempotency_records_expiry", "idempotency_records", ["expires_at"])

    op.execute(
        """
        CREATE OR REPLACE VIEW event_availability AS
        WITH sold AS (
            SELECT event_id, SUM(quantity)::bigint AS sold_quantity
            FROM orders
            GROUP BY event_id
        ), held AS (
            SELECT event_id, SUM(quantity)::bigint AS held_quantity
            FROM holds
            WHERE status = 'active' AND expires_at > CURRENT_TIMESTAMP
            GROUP BY event_id
        )
        SELECT
            events.id AS event_id,
            events.catalog_key,
            events.capacity,
            COALESCE(sold.sold_quantity, 0)::bigint AS sold_quantity,
            COALESCE(held.held_quantity, 0)::bigint AS held_quantity,
            events.capacity::bigint
                - COALESCE(sold.sold_quantity, 0)::bigint
                - COALESCE(held.held_quantity, 0)::bigint AS available_quantity
        FROM events
        LEFT JOIN sold ON sold.event_id = events.id
        LEFT JOIN held ON held.event_id = events.id
        """
    )
    op.execute(
        """
        COMMENT ON VIEW event_availability IS
        'Inventory-owned derived availability authority: capacity minus completed orders and active unexpired holds. No mutable available counter.'
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION eventhub_reject_purchase_attempt_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'purchase_attempts is append-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER purchase_attempts_append_only
        BEFORE UPDATE OR DELETE ON purchase_attempts
        FOR EACH ROW
        EXECUTE FUNCTION eventhub_reject_purchase_attempt_mutation();
        """
    )
    op.execute(
        """
        COMMENT ON TABLE idempotency_records IS
        '[TEMPORARY_MVP_DEFAULT] Buyer-scoped bounded replay records only; frozen requirements do not close production idempotency acceptance.'
        """
    )
    op.execute(
        """
        COMMENT ON TABLE holds IS
        '[TEMPORARY_MVP_DEFAULT] Ten-minute active hold boundary; release, expiry, payment-failure, cancellation, and conversion mechanics remain provisional MVP seams.'
        """
    )
    op.execute(
        """
        COMMENT ON TABLE purchase_attempts IS
        '[TEMPORARY_MVP_DEFAULT] Append-only purchase-attempt projection; audit durability across rollback, crash, and write failure remains explicitly open.'
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS purchase_attempts_append_only ON purchase_attempts")
    op.execute("DROP FUNCTION IF EXISTS eventhub_reject_purchase_attempt_mutation()")
    op.execute("DROP VIEW IF EXISTS event_availability")
    op.drop_index("ix_idempotency_records_expiry", table_name="idempotency_records")
    op.drop_table("idempotency_records")
