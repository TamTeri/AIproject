"""Fixtures for tests that need a real PostgreSQL.

Set EVENTHUB_TEST_DATABASE_URL (see README). Without it these tests skip,
so the unit and contract suites still run anywhere.
"""

from __future__ import annotations

import os

import pytest

from app.db.operations import reset_database, seed_database
from app.db.transaction import PostgresDatabase


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("EVENTHUB_TEST_DATABASE_URL")
    if not url:
        pytest.skip("EVENTHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return url


@pytest.fixture
def seeded_database(database_url: str):
    """A freshly reset and seeded database for each test."""
    reset_database(database_url, environment="test", reset_enabled=True)
    seed_database(database_url)
    database = PostgresDatabase(database_url)
    yield database
    database.dispose()
