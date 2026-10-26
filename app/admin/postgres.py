"""PostgreSQL adapter for the administrator area."""

from __future__ import annotations

from decimal import Decimal

from app.admin.service import AuditRow, RateRow
from app.db.transaction import SqlTransaction, db_id


class PostgresAdminRepository:
    def __init__(self, tx: SqlTransaction) -> None:
        self._tx = tx

    def list_rates(self) -> list[RateRow]:
        rows = self._tx.fetch_all(
            """
            SELECT c.code, r.rate, r.updated_at, a.normalized_email AS updated_by
            FROM currencies c
            JOIN exchange_rates r ON r.currency_code = c.code
            LEFT JOIN accounts a ON a.id = r.updated_by
            WHERE c.enabled ORDER BY c.code
            """
        )
        return [RateRow(r["code"], Decimal(str(r["rate"])), r["updated_at"], r["updated_by"]) for r in rows]

    def currency_enabled(self, code: str) -> bool:
        row = self._tx.fetch_one(
            "SELECT 1 AS ok FROM currencies WHERE code = :code AND enabled", {"code": code}
        )
        return row is not None

    def upsert_rate(self, *, currency: str, rate: Decimal, admin_id: str) -> None:
        self._tx.execute(
            """
            INSERT INTO exchange_rates (currency_code, rate, updated_at, updated_by)
            VALUES (:code, :rate, CURRENT_TIMESTAMP, :admin)
            ON CONFLICT (currency_code) DO UPDATE
            SET rate = EXCLUDED.rate, updated_at = EXCLUDED.updated_at, updated_by = EXCLUDED.updated_by
            """,
            {"code": currency, "rate": rate, "admin": db_id(admin_id)},
        )

    def list_attempts(self, *, limit: int, before_id: str | None) -> list[AuditRow]:
        rows = self._tx.fetch_all(
            """
            SELECT p.id, p.submitted_at, a.normalized_email AS buyer_email, e.title AS event_title,
                   p.quantity_raw, p.currency_raw, p.outcome, p.reason_code, p.order_id
            FROM purchase_attempts p
            LEFT JOIN accounts a ON a.id = p.buyer_id
            LEFT JOIN events e ON e.id = p.event_id
            WHERE (CAST(:before AS BIGINT) IS NULL OR p.id < CAST(:before AS BIGINT))
            ORDER BY p.id DESC
            LIMIT :limit
            """,
            {"before": db_id(before_id) if before_id else None, "limit": limit},
        )
        return [
            AuditRow(
                id=str(r["id"]),
                submitted_at=r["submitted_at"],
                buyer_email=r["buyer_email"],
                event_title=r["event_title"],
                quantity=r["quantity_raw"],
                currency=r["currency_raw"],
                outcome=r["outcome"],
                reason_code=r["reason_code"],
                order_id=str(r["order_id"]) if r["order_id"] is not None else None,
            )
            for r in rows
        ]
