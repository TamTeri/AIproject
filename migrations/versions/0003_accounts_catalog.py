"""Create accounts, session support, and catalog event tables.

Revision ID: 0003_accounts_catalog
Revises: 0002_reference_config
Create Date: 2026-10-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_accounts_catalog"
down_revision = "0002_reference_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "preferred_currency",
            sa.String(length=3),
            sa.ForeignKey("currencies.code", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="buyer"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_authenticated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "sessions_revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 200", name="ck_accounts_name"),
        sa.CheckConstraint(
            "char_length(normalized_email) BETWEEN 3 AND 320",
            name="ck_accounts_email_length",
        ),
        sa.CheckConstraint(
            "role IN ('buyer', 'administrator')",
            name="ck_accounts_role",
        ),
    )
    op.create_index("ix_accounts_role", "accounts", ["role"])

    op.create_table(
        "account_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "account_id",
            sa.BigInteger(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(token_hash) BETWEEN 32 AND 128", name="ck_sessions_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_sessions_expiry_after_creation"),
        sa.CheckConstraint("last_seen_at >= created_at", name="ck_sessions_last_seen"),
    )
    op.create_index(
        "ix_account_sessions_active",
        "account_sessions",
        ["account_id", "expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("catalog_key", sa.String(length=96), nullable=False, unique=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("artist", sa.String(length=200), nullable=False),
        sa.Column("venue", sa.String(length=200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("host_type", sa.String(length=32), nullable=False),
        sa.Column("base_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("char_length(catalog_key) BETWEEN 1 AND 96", name="ck_events_catalog_key"),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_events_title"),
        sa.CheckConstraint("char_length(artist) BETWEEN 1 AND 200", name="ck_events_artist"),
        sa.CheckConstraint("char_length(venue) BETWEEN 1 AND 200", name="ck_events_venue"),
        sa.CheckConstraint("base_price_minor >= 0", name="ck_events_base_price_minor"),
        sa.CheckConstraint("capacity > 0", name="ck_events_capacity_positive"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_events_status"),
    )
    op.create_index("ix_events_artist", "events", ["artist"])
    op.create_index("ix_events_venue", "events", ["venue"])
    op.create_index("ix_events_starts_at", "events", ["starts_at"])

    op.create_table(
        "exchange_rates",
        sa.Column(
            "currency_code",
            sa.String(length=3),
            sa.ForeignKey("currencies.code", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("rate", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("rate > 0", name="ck_exchange_rates_positive"),
    )


def downgrade() -> None:
    op.drop_table("exchange_rates")
    op.drop_index("ix_events_starts_at", table_name="events")
    op.drop_index("ix_events_venue", table_name="events")
    op.drop_index("ix_events_artist", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_account_sessions_active", table_name="account_sessions")
    op.drop_table("account_sessions")
    op.drop_index("ix_accounts_role", table_name="accounts")
    op.drop_table("accounts")
