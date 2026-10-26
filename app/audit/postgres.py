"""PostgreSQL audit sink. ``purchase_attempts`` is append-only: a database
trigger rejects UPDATE and DELETE, and this adapter only ever INSERTs."""

from __future__ import annotations

from app.audit.models import PurchaseAttemptAudit
from app.db.transaction import db_id


class PostgresAuditLog:
    def append(self, *, tx, record: PurchaseAttemptAudit) -> None:
        tx.execute(
            """
            INSERT INTO purchase_attempts (submitted_at, buyer_id, event_id, quantity_raw,
                currency_raw, outcome, reason_code, request_id, idempotency_key, hold_id, order_id)
            VALUES (:submitted_at, :buyer_id, :event_id, :quantity, :currency, :outcome,
                :reason_code, :request_id, :idempotency_key, :hold_id, :order_id)
            """,
            {
                "submitted_at": record.submitted_at,
                "buyer_id": db_id(record.buyer_id),
                "event_id": db_id(record.event_id),
                "quantity": record.quantity,
                "currency": record.currency,
                "outcome": record.outcome,
                "reason_code": record.reason_code,
                "request_id": record.request_id,
                "idempotency_key": record.idempotency_key,
                "hold_id": db_id(record.hold_id),
                "order_id": db_id(record.order_id),
            },
        )
