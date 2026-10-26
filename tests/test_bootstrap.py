from __future__ import annotations

import os
import subprocess
import sys

import pytest


def test_app_factory_exposes_health_and_postgresql_configuration():
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_URL": "postgresql+psycopg://eventhub:eventhub@localhost:5432/eventhub_test",
        }
    )

    response = app.test_client().get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"service": "eventhub", "status": "ok"}
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql+psycopg://")


def test_migration_seed_and_reset_entrypoints_round_trip_bootstrap_fixture():
    database_url = os.environ.get("EVENTHUB_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("EVENTHUB_TEST_DATABASE_URL is required for the real PostgreSQL bootstrap check")

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": database_url,
            "EVENTHUB_ENVIRONMENT": "test",
            "EVENTHUB_RESET_ENABLED": "true",
        }
    )

    def run(command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "app.config.commands", command],
            check=False,
            env=env,
            text=True,
            capture_output=True,
        )

    reset = run("reset")
    assert reset.returncode == 0, reset.stderr

    migrate = run("migrate")
    assert migrate.returncode == 0, migrate.stderr

    seed = run("seed")
    assert seed.returncode == 0, seed.stderr

    repeat_seed = run("seed")
    assert repeat_seed.returncode == 0, repeat_seed.stderr

    import psycopg

    direct_database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(direct_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM eventhub_bootstrap")
            assert cursor.fetchone() == (1,)
            cursor.execute("SELECT key FROM eventhub_bootstrap")
            assert cursor.fetchone() == ("bootstrap",)

    reset_again = run("reset")
    assert reset_again.returncode == 0, reset_again.stderr

    with psycopg.connect(direct_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM eventhub_bootstrap")
            assert cursor.fetchone() == (0,)
