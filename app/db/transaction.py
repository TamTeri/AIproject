from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from urllib.parse import urlparse

from sqlalchemy import Connection, Engine, create_engine


class PostgresDatabase:
    """Own one SQLAlchemy engine and one transaction per unit-of-work scope.

    The yielded connection is the transaction seam passed to repositories. The
    context manager commits on normal exit and rolls back on any exception.
    Repositories must not commit or roll back this connection themselves.
    """

    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        _validate_postgresql_url(database_url)
        self.database_url = database_url
        self._engine = engine or create_engine(database_url, pool_pre_ping=True)

    @property
    def engine(self) -> Engine:
        return self._engine

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self._engine.begin() as connection:
            yield connection

    def dispose(self) -> None:
        self._engine.dispose()


@contextmanager
def transaction_scope(database: PostgresDatabase | str) -> Iterator[Connection]:
    """Yield a caller-owned PostgreSQL transaction connection.

    A string creates and disposes a short-lived database owner. Passing a
    ``PostgresDatabase`` preserves its engine for the caller's lifetime.
    """
    owner = database if isinstance(database, PostgresDatabase) else PostgresDatabase(database)
    try:
        with owner.transaction() as connection:
            yield connection
    finally:
        if not isinstance(database, PostgresDatabase):
            owner.dispose()


def _validate_postgresql_url(database_url: str) -> None:
    scheme = urlparse(database_url).scheme.lower()
    if scheme not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("EventHub database transactions require PostgreSQL")
