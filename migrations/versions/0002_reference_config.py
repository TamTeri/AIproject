"""Create currency and policy/configuration tables.

Revision ID: 0002_reference_config
Revises: 0001_bootstrap
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_reference_config"
down_revision = "0001_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "currencies",
        sa.Column("code", sa.String(length=3), primary_key=True),
        sa.Column("minor_unit", sa.SmallInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "code = upper(code) AND char_length(code) = 3",
            name="ck_currencies_code_format",
        ),
        sa.CheckConstraint(
            "minor_unit BETWEEN 0 AND 4",
            name="ck_currencies_minor_unit",
        ),
    )

    op.create_table(
        "app_config",
        sa.Column("config_key", sa.String(length=96), primary_key=True),
        sa.Column("value_json", postgresql.JSONB(), nullable=False),
        sa.Column("policy_status", sa.String(length=96), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "char_length(config_key) BETWEEN 1 AND 96",
            name="ck_app_config_key_length",
        ),
        sa.CheckConstraint(
            "policy_status IN ('[TEMPORARY_MVP_DEFAULT]', '[TEMPORARY_MVP_DEFAULT] [PROVISIONAL_LOCAL_ONLY]', '[TEAM]', '[OPEN]')",
            name="ck_app_config_policy_status",
        ),
    )
    op.create_index("ix_app_config_policy_status", "app_config", ["policy_status"])


def downgrade() -> None:
    op.drop_index("ix_app_config_policy_status", table_name="app_config")
    op.drop_table("app_config")
    op.drop_table("currencies")
