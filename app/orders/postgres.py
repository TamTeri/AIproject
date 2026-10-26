"""PostgreSQL adapters for orders: write (inside the purchase transaction) and
buyer-scoped reads for order history."""

from __future__ import annotations

import json

from app.db.transaction import SqlTransaction, db_id
from app.orders.models import OrderSnapshot


class PostgresOrderWriter:
    """Implements ``OrderSnapshotPort.create_order_snapshot``. Orders copy the
    quote frozen at hold time; they never recalculate a price."""

    def create_order_snapshot(self, *, tx, buyer_id, hold, quote_snapshot) -> OrderSnapshot:
        row = tx.fetch_one(
            """
            INSERT INTO orders (buyer_id, event_id, hold_id, quantity, currency_code,
                                rate_applied, discount_minor, total_minor, quote_snapshot, created_at)
            VALUES (:buyer_id, :event_id, :hold_id, :quantity, :currency, :rate, :discount,
                    :total, CAST(:snapshot AS JSONB), CURRENT_TIMESTAMP)
            RETURNING id
            """,
            {
                "buyer_id": db_id(buyer_id),
                "event_id": db_id(hold.event_id),
                "hold_id": db_id(hold.id),
                "quantity": hold.quantity,
                "currency": quote_snapshot.currency,
                "rate": quote_snapshot.exchange_rate,
                "discount": quote_snapshot.discount_minor,
                "total": quote_snapshot.total_minor,
                "snapshot": json.dumps(quote_snapshot.to_json()),
            },
        )
        return OrderSnapshot(
            id=str(row["id"]),
            buyer_id=str(buyer_id),
            event_id=str(hold.event_id),
            hold_id=str(hold.id),
            quantity=hold.quantity,
            currency=quote_snapshot.currency,
            exchange_rate=quote_snapshot.exchange_rate,
            total_minor=quote_snapshot.total_minor,
            quote_snapshot=quote_snapshot,
        )


_READ = """
    SELECT o.id, o.quantity, o.currency_code AS currency, o.rate_applied, o.discount_minor,
           o.total_minor, o.quote_snapshot, o.created_at,
           e.title, e.artist, e.venue, e.starts_at
    FROM orders o JOIN events e ON e.id = o.event_id
    WHERE o.buyer_id = :buyer_id
"""


class PostgresOrderReader:
    def __init__(self, tx: SqlTransaction) -> None:
        self._tx = tx

    def list_for_buyer(self, buyer_id: str, *, limit: int) -> list[dict]:
        return self._tx.fetch_all(
            _READ + " ORDER BY o.created_at DESC, o.id DESC LIMIT :limit",
            {"buyer_id": db_id(buyer_id), "limit": limit},
        )

    def get_for_buyer(self, buyer_id: str, order_id: str) -> dict | None:
        return self._tx.fetch_one(
            _READ + " AND o.id = :order_id", {"buyer_id": db_id(buyer_id), "order_id": db_id(order_id)}
        )
