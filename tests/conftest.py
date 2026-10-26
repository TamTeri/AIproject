"""Shared pytest bootstrap fixtures."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def eventhub_test_database_url() -> str:
    url = os.environ.get("EVENTHUB_TEST_DATABASE_URL")
    if not url:
        pytest.skip("EVENTHUB_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return url
