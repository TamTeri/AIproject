"""PostgreSQL adapters for identity: ``accounts`` and ``account_sessions``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.db.transaction import SqlTransaction, db_id
from app.identity.contracts import AccountRecord
from app.identity.repository import DuplicateEmailError
from app.identity.sessions import SessionRecord

_ACCOUNT_COLUMNS = "id, name, normalized_email, password_hash, created_at, role, preferred_currency"


def _record(row: dict | None) -> AccountRecord | None:
    if row is None:
        return None
    return AccountRecord(
        account_id=str(row["id"]),
        name=row["name"],
        normalized_email=row["normalized_email"],
        password_hash=row["password_hash"],
        created_at=row["created_at"],
        role=row["role"],
        preferred_currency=row["preferred_currency"],
    )


class PostgresAccountRepository:
    def __init__(self, tx: SqlTransaction) -> None:
        self._tx = tx

    def find_by_normalized_email(self, normalized_email: str) -> AccountRecord | None:
        return _record(
            self._tx.fetch_one(
                f"SELECT {_ACCOUNT_COLUMNS} FROM accounts WHERE normalized_email = :email",
                {"email": normalized_email},
            )
        )

    def find_by_id(self, account_id: str) -> AccountRecord | None:
        key = db_id(account_id)
        if key is None:
            return None
        return _record(
            self._tx.fetch_one(f"SELECT {_ACCOUNT_COLUMNS} FROM accounts WHERE id = :id", {"id": key})
        )

    def insert(
        self, *, name: str, normalized_email: str, password_hash: str, created_at: datetime
    ) -> AccountRecord:
        # A savepoint keeps the outer transaction usable if the unique index wins a race.
        savepoint = self._tx.connection.begin_nested()
        try:
            row = self._tx.fetch_one(
                f"""
                INSERT INTO accounts (name, normalized_email, password_hash, created_at)
                VALUES (:name, :email, :hash, :created_at)
                RETURNING {_ACCOUNT_COLUMNS}
                """,
                {"name": name, "email": normalized_email, "hash": password_hash, "created_at": created_at},
            )
            savepoint.commit()
        except IntegrityError as exc:
            savepoint.rollback()
            raise DuplicateEmailError(normalized_email) from exc
        return _record(row)

    def set_preferred_currency(self, account_id: str, currency: str) -> None:
        self._tx.execute(
            "UPDATE accounts SET preferred_currency = :currency WHERE id = :id",
            {"currency": currency, "id": db_id(account_id)},
        )

    def set_role(self, account_id: str, role: str) -> None:
        self._tx.execute(
            "UPDATE accounts SET role = :role WHERE id = :id", {"role": role, "id": db_id(account_id)}
        )

    def mark_authenticated(self, account_id: str, now: datetime) -> None:
        self._tx.execute(
            "UPDATE accounts SET last_authenticated_at = :now WHERE id = :id",
            {"now": now, "id": db_id(account_id)},
        )


class PostgresSessionRepository:
    def __init__(self, tx: SqlTransaction) -> None:
        self._tx = tx

    def insert(self, *, account_id: str, token_hash: str, created_at: datetime, expires_at: datetime) -> None:
        self._tx.execute(
            """
            INSERT INTO account_sessions (account_id, token_hash, created_at, last_seen_at, expires_at)
            VALUES (:account_id, :token_hash, :created_at, :created_at, :expires_at)
            """,
            {
                "account_id": db_id(account_id),
                "token_hash": token_hash,
                "created_at": created_at,
                "expires_at": expires_at,
            },
        )

    def find_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        row = self._tx.fetch_one(
            """
            SELECT id, account_id, last_seen_at, expires_at, revoked_at
            FROM account_sessions WHERE token_hash = :token_hash
            """,
            {"token_hash": token_hash},
        )
        if row is None:
            return None
        return SessionRecord(
            session_id=str(row["id"]),
            account_id=str(row["account_id"]),
            last_seen_at=row["last_seen_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
        )

    def touch(self, session_id: str, *, now: datetime) -> None:
        self._tx.execute(
            "UPDATE account_sessions SET last_seen_at = GREATEST(last_seen_at, :now) WHERE id = :id",
            {"now": now, "id": db_id(session_id)},
        )

    def revoke(self, session_id: str, *, now: datetime) -> None:
        self._tx.execute(
            "UPDATE account_sessions SET revoked_at = :now WHERE id = :id AND revoked_at IS NULL",
            {"now": now, "id": db_id(session_id)},
        )
