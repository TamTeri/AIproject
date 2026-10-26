from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC
from pathlib import Path

from app.db.operations import (
    DatabaseResetError,
    database_url_from_environment,
    migrate_database,
    reset_database,
    seed_database,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EventHub shared PostgreSQL database commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("migrate", "seed", "reset"):
        subparsers.add_parser(name)
    subparsers.add_parser(
        "create-admin",
        help="Create or promote an administrator from EVENTHUB_ADMIN_EMAIL / "
        "EVENTHUB_ADMIN_PASSWORD / EVENTHUB_ADMIN_NAME (seed/config-only provisioning).",
    )
    args = parser.parse_args(argv)

    try:
        database_url = database_url_from_environment()
        if args.command == "create-admin":
            print(create_admin(database_url))
        elif args.command == "migrate":
            migrate_database(database_url)
            print("migrated shared schema to head")
        elif args.command == "seed":
            seed_path = Path(
                os.environ.get("EVENTHUB_DB_SEED_FILE", str(PROJECT_ROOT / "seed" / "catalog.json"))
            )
            seed_database(database_url, fixture_path=seed_path)
            print(f"seeded shared schema from {seed_path}")
        else:
            environment = os.environ.get("EVENTHUB_ENVIRONMENT")
            if not environment:
                raise DatabaseResetError("EVENTHUB_ENVIRONMENT must be explicit for a destructive reset")
            reset_database(
                database_url,
                environment=environment,
                reset_enabled=_boolean_environment("EVENTHUB_RESET_ENABLED"),
            )
            print("reset shared schema to head without seed data")
        return 0
    except (DatabaseResetError, OSError, RuntimeError, ValueError) as exc:
        print(f"eventhub database error: {exc}", file=sys.stderr)
        return 2


def create_admin(database_url: str) -> str:
    """[TEMPORARY_MVP_DEFAULT] ADR-004: administrators exist only through this
    operator command; there is no self-service promotion in the web app."""
    from datetime import datetime

    from app.db.transaction import PostgresDatabase, unit_of_work
    from app.identity.contracts import RegisterInput
    from app.identity.policy import normalize_email
    from app.identity.postgres import PostgresAccountRepository
    from app.identity.service import IdentityService

    email = normalize_email(os.environ.get("EVENTHUB_ADMIN_EMAIL", ""))
    database = PostgresDatabase(database_url)
    try:
        with unit_of_work(database) as tx:
            accounts = PostgresAccountRepository(tx)
            existing = accounts.find_by_normalized_email(email)
            if existing is None:
                password = os.environ.get("EVENTHUB_ADMIN_PASSWORD", "")
                name = os.environ.get("EVENTHUB_ADMIN_NAME", "EventHub Administrator")
                account = IdentityService(account_repository=accounts).register(
                    RegisterInput(name=name, email=email, password=password),
                    now=datetime.now(UTC),
                )
                account_id = account.account_id
            else:
                account_id = existing.account_id
            accounts.set_role(account_id, "administrator")
    finally:
        database.dispose()
    return f"administrator ready: {email}"


def _boolean_environment(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise DatabaseResetError(f"{name} must be an explicit boolean")


if __name__ == "__main__":
    raise SystemExit(main())
