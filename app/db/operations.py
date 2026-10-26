from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine

from app.config.database import alembic_config
from app.db.transaction import _validate_postgresql_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED_FILE = PROJECT_ROOT / "seed" / "catalog.json"


class DatabaseResetError(RuntimeError):
    """Raised when a destructive reset is not explicitly allowed."""


def migrate_database(database_url: str) -> None:
    _validate_postgresql_url(database_url)
    command.upgrade(alembic_config(database_url=database_url), "head")


def seed_database(database_url: str, *, fixture_path: Path | None = None) -> None:
    _validate_postgresql_url(database_url)
    migrate_database(database_url)

    from app.db.seed import load_seed_fixture, seed_connection

    fixture = load_seed_fixture(fixture_path or DEFAULT_SEED_FILE)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            seed_connection(connection, fixture)
    finally:
        engine.dispose()


def reset_database(
    database_url: str,
    *,
    environment: str,
    reset_enabled: bool,
) -> None:
    """Reset a disposable database, then leave it migrated but unseeded."""
    _validate_postgresql_url(database_url)
    _require_reset_enabled(environment=environment, reset_enabled=reset_enabled)

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
            connection.exec_driver_sql("CREATE SCHEMA public")
    finally:
        engine.dispose()

    migrate_database(database_url)


def database_url_from_environment(values: Mapping[str, object] | None = None) -> str:
    source = dict(os.environ)
    if values:
        source.update(values)
    database_url = str(source.get("DATABASE_URL") or source.get("EVENTHUB_DATABASE_URL") or "").strip()
    if not database_url:
        raise DatabaseResetError("DATABASE_URL is required")
    _validate_postgresql_url(database_url)
    return database_url


def _require_reset_enabled(*, environment: str, reset_enabled: bool) -> None:
    if not reset_enabled:
        raise DatabaseResetError("database reset requires EVENTHUB_RESET_ENABLED=true")
    if environment not in {"local", "development", "test"}:
        raise DatabaseResetError("database reset is only allowed in local, development, or test environments")
