from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Connection, Engine, create_engine, text


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


class SqlTransaction:
    """Explicit commit/rollback transaction used by the purchase coordinator.

    Implements ``app.purchase.ports.PostgresTransactionContext``. Repositories
    run SQL through it but never commit or roll back themselves.
    """

    def __init__(self, engine: Engine) -> None:
        self._connection = engine.connect()
        self._transaction = self._connection.begin()
        self._closed = False

    @property
    def connection(self) -> Connection:
        return self._connection

    def execute(self, statement: str, parameters: Mapping[str, object] | None = None) -> Any:
        return self._connection.execute(text(statement), dict(parameters or {}))

    def fetch_one(
        self, statement: str, parameters: Mapping[str, object] | None = None
    ) -> Mapping[str, Any] | None:
        row = self.execute(statement, parameters).mappings().first()
        return dict(row) if row is not None else None

    def fetch_all(
        self, statement: str, parameters: Mapping[str, object] | None = None
    ) -> list[Mapping[str, Any]]:
        return [dict(row) for row in self.execute(statement, parameters).mappings().all()]

    def commit(self) -> None:
        if not self._closed:
            self._transaction.commit()
            self._close()

    def rollback(self) -> None:
        if not self._closed:
            self._transaction.rollback()
            self._close()

    def _close(self) -> None:
        self._closed = True
        self._connection.close()


class SqlTransactionProvider:
    """Implements ``app.purchase.ports.TransactionProvider`` for PostgreSQL."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def begin(self) -> SqlTransaction:
        return SqlTransaction(self._database.engine)


@contextmanager
def unit_of_work(database: PostgresDatabase) -> Iterator[SqlTransaction]:
    """One transaction for a non-purchase request: commit on success, else roll back."""
    tx = SqlTransaction(database.engine)
    try:
        yield tx
    except BaseException:
        tx.rollback()
        raise
    tx.commit()


def db_id(value: object) -> int | None:
    """Convert a string id from a URL/session into a BIGINT, or None if invalid."""
    text_value = str(value).strip() if value is not None else ""
    if not text_value.isdigit() or len(text_value) > 18:
        return None
    return int(text_value)
