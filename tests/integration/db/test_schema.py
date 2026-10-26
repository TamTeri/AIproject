from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError, IntegrityError

from app.db import PostgresDatabase, migrate_database, reset_database, seed_database


ROOT = Path(__file__).resolve().parents[3]
SEED_FILE = ROOT / "seed" / "catalog.json"


def _direct_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _run_db_command(database_url: str, command: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": database_url,
            "EVENTHUB_ENVIRONMENT": "test",
            "EVENTHUB_RESET_ENABLED": "true",
            "EVENTHUB_DB_SEED_FILE": str(SEED_FILE),
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "app.db.commands", command],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def database_engine(eventhub_test_database_url: str):
    engine = create_engine(eventhub_test_database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def migrated_seeded_database(eventhub_test_database_url: str, database_engine):
    reset_database(
        eventhub_test_database_url,
        environment="test",
        reset_enabled=True,
    )
    migrate_database(eventhub_test_database_url)
    seed_database(eventhub_test_database_url, fixture_path=SEED_FILE)
    yield eventhub_test_database_url
    reset_database(
        eventhub_test_database_url,
        environment="test",
        reset_enabled=True,
    )


def test_fresh_migrate_seed_repeat_seed_and_reset_are_deterministic(
    eventhub_test_database_url: str,
):
    reset = _run_db_command(eventhub_test_database_url, "reset")
    assert reset.returncode == 0, reset.stderr

    migrate = _run_db_command(eventhub_test_database_url, "migrate")
    assert migrate.returncode == 0, migrate.stderr

    seed = _run_db_command(eventhub_test_database_url, "seed")
    assert seed.returncode == 0, seed.stderr
    repeat_seed = _run_db_command(eventhub_test_database_url, "seed")
    assert repeat_seed.returncode == 0, repeat_seed.stderr

    engine = create_engine(eventhub_test_database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    text(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                        ORDER BY table_name
                        """
                    )
                )
            }
            assert {
                "eventhub_bootstrap",
                "accounts",
                "account_sessions",
                "events",
                "currencies",
                "exchange_rates",
                "app_config",
                "holds",
                "orders",
                "purchase_attempts",
                "idempotency_records",
            } <= tables

            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert revision == "0005_schema_seams"

            assert connection.execute(text("SELECT count(*) FROM currencies")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM exchange_rates")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM app_config")).scalar_one() >= 4
            assert connection.execute(text("SELECT count(*) FROM events")).scalar_one() == 1
            event = connection.execute(
                text(
                    """
                    SELECT catalog_key, base_price_minor, capacity
                    FROM events
                    ORDER BY id
                    """
                )
            ).one()
            assert event == ("demo-usf-concert-2026-11-01", 2500, 100)

            currency = connection.execute(
                text("SELECT code, minor_unit, enabled FROM currencies")
            ).one()
            assert currency == ("USD", 2, True)
            rate = connection.execute(
                text("SELECT currency_code, rate FROM exchange_rates")
            ).one()
            assert rate == ("USD", Decimal("1.00000000"))

            config_rows = connection.execute(
                text(
                    """
                    SELECT config_key, policy_status
                    FROM app_config
                    ORDER BY config_key
                    """
                )
            ).all()
            assert config_rows
            assert {row[1] for row in config_rows} == {
                "[TEMPORARY_MVP_DEFAULT] [PROVISIONAL_LOCAL_ONLY]"
            }

            availability = connection.execute(
                text(
                    """
                    SELECT catalog_key, available_quantity, held_quantity, sold_quantity
                    FROM event_availability
                    """
                )
            ).one()
            assert availability == ("demo-usf-concert-2026-11-01", 100, 0, 0)

            assert connection.execute(
                text("SELECT count(*) FROM eventhub_bootstrap")
            ).scalar_one() == 1
    finally:
        engine.dispose()

    reset_again = _run_db_command(eventhub_test_database_url, "reset")
    assert reset_again.returncode == 0, reset_again.stderr

    engine = create_engine(eventhub_test_database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM events")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM currencies")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM app_config")).scalar_one() == 0
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "0005_schema_seams"
    finally:
        engine.dispose()


def test_one_postgresql_transaction_connection_commits_or_rolls_back_as_a_unit(
    migrated_seeded_database: str,
):
    database = PostgresDatabase(migrated_seeded_database)

    with database.transaction() as transaction:
        account_id = transaction.execute(
            text(
                """
                INSERT INTO accounts (name, normalized_email, password_hash)
                VALUES (:name, :email, :password_hash)
                RETURNING id
                """
            ),
            {
                "name": "Tracer Buyer",
                "email": "tracer@example.test",
                "password_hash": "$argon2id$v=19$temporary-test-hash",
            },
        ).scalar_one()
        transaction.execute(
            text(
                """
                INSERT INTO account_sessions
                    (account_id, token_hash, expires_at)
                VALUES
                    (:account_id, :token_hash, CURRENT_TIMESTAMP + INTERVAL '30 minutes')
                """
            ),
            {"account_id": account_id, "token_hash": "a" * 64},
        )

    with database.transaction() as transaction:
        assert transaction.execute(
            text("SELECT count(*) FROM account_sessions WHERE token_hash = :token_hash"),
            {"token_hash": "a" * 64},
        ).scalar_one() == 1

    with pytest.raises(RuntimeError, match="rollback marker"):
        with database.transaction() as transaction:
            transaction.execute(
                text(
                    """
                    INSERT INTO accounts (name, normalized_email, password_hash)
                    VALUES (:name, :email, :password_hash)
                    """
                ),
                {
                    "name": "Rolled Back",
                    "email": "rollback@example.test",
                    "password_hash": "$argon2id$v=19$temporary-test-hash",
                },
            )
            raise RuntimeError("rollback marker")

    with database.transaction() as transaction:
        assert transaction.execute(
            text("SELECT count(*) FROM accounts WHERE normalized_email = :email"),
            {"email": "rollback@example.test"},
        ).scalar_one() == 0

    database.dispose()


def test_postgresql_constraints_cover_ownership_state_and_bounded_temporary_records(
    migrated_seeded_database: str,
    database_engine,
):
    with database_engine.begin() as connection:
        account_id = connection.execute(
            text(
                """
                INSERT INTO accounts (name, normalized_email, password_hash)
                VALUES (:name, :email, :password_hash)
                RETURNING id
                """
            ),
            {
                "name": "Constraint Buyer",
                "email": "constraints@example.test",
                "password_hash": "$argon2id$v=19$temporary-test-hash",
            },
        ).scalar_one()
        event_id = connection.execute(
            text(
                "SELECT id FROM events WHERE catalog_key = 'demo-usf-concert-2026-11-01'"
            )
        ).scalar_one()

    def assert_rejected(statement: str, parameters: dict[str, object] | None = None):
        with pytest.raises((IntegrityError, DatabaseError)):
            with database_engine.begin() as connection:
                connection.execute(text(statement), parameters or {})

    assert_rejected(
        """
        INSERT INTO accounts (name, normalized_email, password_hash)
        VALUES ('Duplicate', 'constraints@example.test', 'hash')
        """
    )
    assert_rejected(
        """
        INSERT INTO currencies (code, minor_unit)
        VALUES ('BAD', 5)
        """
    )
    assert_rejected(
        """
        INSERT INTO events
            (catalog_key, title, artist, venue, starts_at, host_type, base_price_minor, capacity)
        VALUES
            ('invalid-capacity', 'Invalid', 'Invalid', 'Invalid', CURRENT_TIMESTAMP,
             'external', 100, 0)
        """
    )
    assert_rejected(
        """
        INSERT INTO account_sessions (account_id, token_hash, expires_at, created_at)
        VALUES (:account_id, :token_hash, TIMESTAMPTZ '2026-10-26 12:00:00+00',
                TIMESTAMPTZ '2026-10-26 12:00:00+00')
        """,
        {"account_id": account_id, "token_hash": "b" * 64},
    )
    assert_rejected(
        """
        INSERT INTO holds (event_id, buyer_id, quantity, status, expires_at)
        VALUES (:event_id, :account_id, 0, 'active', CURRENT_TIMESTAMP + INTERVAL '10 minutes')
        """,
        {"event_id": event_id, "account_id": account_id},
    )

    hold_id = None
    with database_engine.begin() as connection:
        hold_id = connection.execute(
            text(
                """
                INSERT INTO holds
                    (event_id, buyer_id, quantity, status, expires_at, quote_snapshot)
                VALUES
                    (:event_id, :account_id, 1, 'active',
                     CURRENT_TIMESTAMP + INTERVAL '10 minutes', '{"currency":"USD"}'::jsonb)
                RETURNING id
                """
            ),
            {"event_id": event_id, "account_id": account_id},
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO idempotency_records
                    (buyer_id, idempotency_key, request_hash, state, expires_at,
                     policy_status)
                VALUES
                    (:account_id, 'temporary-key', :request_hash, 'in_progress',
                     CURRENT_TIMESTAMP + INTERVAL '30 minutes',
                     '[TEMPORARY_MVP_DEFAULT]')
                """
            ),
            {"account_id": account_id, "request_hash": "c" * 64},
        )

    assert_rejected(
        """
        INSERT INTO idempotency_records
            (buyer_id, idempotency_key, request_hash, state, expires_at, policy_status)
        VALUES
            (:account_id, 'wrong-policy', :request_hash, 'in_progress',
             CURRENT_TIMESTAMP + INTERVAL '30 minutes', '[TEAM]')
        """,
        {"account_id": account_id, "request_hash": "d" * 64},
    )
    assert_rejected(
        """
        INSERT INTO holds
            (event_id, buyer_id, quantity, status, expires_at, terminal_at)
        VALUES
            (:event_id, :account_id, 1, 'active',
             CURRENT_TIMESTAMP + INTERVAL '10 minutes', CURRENT_TIMESTAMP)
        """,
        {"event_id": event_id, "account_id": account_id},
    )

    with database_engine.begin() as connection:
        attempt_id = connection.execute(
            text(
                """
                INSERT INTO purchase_attempts
                    (buyer_id, event_id, quantity_raw, currency_raw, outcome,
                     reason_code, request_id, hold_id)
                VALUES
                    (:account_id, :event_id, 1, 'USD', 'success', 'PURCHASED',
                     'request-1', :hold_id)
                RETURNING id
                """
            ),
            {
                "account_id": account_id,
                "event_id": event_id,
                "hold_id": hold_id,
            },
        ).scalar_one()
        assert attempt_id > 0

    assert_rejected(
        "UPDATE purchase_attempts SET reason_code = 'CHANGED' WHERE id = :attempt_id",
        {"attempt_id": attempt_id},
    )
    assert_rejected(
        "DELETE FROM purchase_attempts WHERE id = :attempt_id",
        {"attempt_id": attempt_id},
    )

    database = PostgresDatabase(migrated_seeded_database)
    try:
        with database.transaction() as transaction:
            assert transaction.execute(
                text(
                    """
                    SELECT policy_status
                    FROM idempotency_records
                    WHERE buyer_id = :account_id AND idempotency_key = 'temporary-key'
                    """
                ),
                {"account_id": account_id},
            ).scalar_one() == "[TEMPORARY_MVP_DEFAULT]"
    finally:
        database.dispose()
