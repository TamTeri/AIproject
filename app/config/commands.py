from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, text

from app.config.database import alembic_config
from app.config.settings import ConfigurationError, Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def migrate() -> int:
    settings = Settings.from_values()
    command.upgrade(alembic_config(database_url=settings.database_url), "head")
    print("migrated to head")
    return 0


def seed() -> int:
    settings = Settings.from_values()
    command.upgrade(alembic_config(database_url=settings.database_url), "head")
    seed_path = _resolve_seed_path(settings.seed_file)
    payload = _load_seed(seed_path)

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            for fixture in payload["fixtures"]:
                connection.execute(
                    text(
                        """
                        INSERT INTO eventhub_bootstrap (key, value)
                        VALUES (:key, CAST(:value AS JSONB))
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value
                        """
                    ),
                    {
                        "key": fixture["key"],
                        "value": json.dumps(fixture["value"], sort_keys=True),
                    },
                )
    finally:
        engine.dispose()

    print(f"seeded {len(payload['fixtures'])} bootstrap fixture(s) from {seed_path}")
    return 0


def reset() -> int:
    settings = Settings.from_values()
    _require_reset_enabled(settings)

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
            connection.exec_driver_sql("CREATE SCHEMA public")
    finally:
        engine.dispose()

    command.upgrade(alembic_config(database_url=settings.database_url), "head")
    print("reset disposable database to head without seed data")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EventHub bootstrap database commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("migrate", "seed", "reset"):
        subparsers.add_parser(name)

    args = parser.parse_args(argv)
    try:
        return {"migrate": migrate, "seed": seed, "reset": reset}[args.command]()
    except (ConfigurationError, OSError, RuntimeError) as exc:
        print(f"eventhub bootstrap error: {exc}", file=sys.stderr)
        return 2


def _resolve_seed_path(seed_file: Path) -> Path:
    path = seed_file if seed_file.is_absolute() else PROJECT_ROOT / seed_file
    if not path.is_file():
        raise ConfigurationError(f"seed file does not exist: {path}")
    return path


def _load_seed(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"invalid seed file: {path}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ConfigurationError("seed file schema_version must be 1")
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ConfigurationError("seed file must contain at least one fixture")

    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise ConfigurationError("each seed fixture must be an object")
        key = fixture.get("key")
        value = fixture.get("value")
        if not isinstance(key, str) or not key or len(key) > 64:
            raise ConfigurationError("seed fixture keys must be 1-64 characters")
        if not isinstance(value, dict):
            raise ConfigurationError("seed fixture values must be JSON objects")

    return payload


def _require_reset_enabled(settings: Settings) -> None:
    if not settings.reset_enabled:
        raise ConfigurationError("database reset is disabled; set EVENTHUB_RESET_ENABLED=true explicitly")
    if settings.environment not in {"local", "development", "test"}:
        raise ConfigurationError("database reset is only allowed in local, development, or test environments")


if __name__ == "__main__":
    raise SystemExit(main())
