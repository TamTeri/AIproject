"""PostgreSQL inventory adapter (inventory-002..007).

Concurrency: the purchase coordinator first locks the event row
(``SELECT ... FOR UPDATE``), so for one event the availability check and the
hold insert run strictly one transaction at a time. Two buyers can never be
given the same ticket (inventory-004). Availability is derived, never stored:
capacity - sold - active unexpired holds.

Hold transitions are conditional on ``status = 'active'``, so a hold is
converted or released at most once, and converting does not subtract
inventory a second time.
"""

from __future__ import annotations

import json
from datetime import datetime

from app.db.transaction import db_id
from app.inventory.models import Hold, HoldReleaseReason, HoldStatus
from app.purchase.models import QuoteSnapshot

_HOLD_COLUMNS = "id, buyer_id, event_id, quantity, status, expires_at, quote_snapshot"


def _hold(row: dict | None) -> Hold | None:
    if row is None:
        return None
    snapshot = row.get("quote_snapshot")
    return Hold(
        id=str(row["id"]),
        buyer_id=str(row["buyer_id"]),
        event_id=str(row["event_id"]),
        quantity=int(row["quantity"]),
        expires_at=row["expires_at"],
        status=HoldStatus(row["status"]),
        quote_snapshot=QuoteSnapshot.from_json(snapshot) if snapshot else None,
    )


class PostgresInventory:
    def expire_stale_holds(self, tx, *, event_id: str, now: datetime) -> int:
        """Mark holds whose ten minutes are up as expired (inventory-006)."""
        result = tx.execute(
            """
            UPDATE holds SET status = 'expired', terminal_at = :now
            WHERE event_id = :event_id AND status = 'active' AND expires_at <= :now
            """,
            {"event_id": db_id(event_id), "now": now},
        )
        return result.rowcount

    def available(self, tx, *, event_id: str, now: datetime) -> int:
        row = tx.fetch_one(
            """
            SELECT e.capacity
                 - COALESCE((SELECT SUM(o.quantity) FROM orders o WHERE o.event_id = e.id), 0)
                 - COALESCE((SELECT SUM(h.quantity) FROM holds h
                             WHERE h.event_id = e.id AND h.status = 'active'
                               AND h.expires_at > :now), 0) AS available
            FROM events e WHERE e.id = :event_id
            """,
            {"event_id": db_id(event_id), "now": now},
        )
        return int(row["available"]) if row else 0

    def allocate_hold(self, *, tx, buyer_id, event_id, quantity, expires_at, quote_snapshot):
        """Caller must already hold the event row lock. None means sold out."""
        row = tx.fetch_one("SELECT CURRENT_TIMESTAMP AS now")
        now = row["now"]
        self.expire_stale_holds(tx, event_id=event_id, now=now)
        if self.available(tx, event_id=event_id, now=now) < quantity:
            return None
        snapshot = quote_snapshot.to_json() if quote_snapshot is not None else None
        created = tx.fetch_one(
            f"""
            INSERT INTO holds (event_id, buyer_id, quantity, status, created_at, expires_at, quote_snapshot)
            VALUES (:event_id, :buyer_id, :quantity, 'active', :now, :expires_at,
                    CAST(:snapshot AS JSONB))
            RETURNING {_HOLD_COLUMNS}
            """,
            {
                "event_id": db_id(event_id),
                "buyer_id": db_id(buyer_id),
                "quantity": quantity,
                "now": now,
                "expires_at": expires_at,
                "snapshot": json.dumps(snapshot) if snapshot is not None else None,
            },
        )
        return _hold(created)

    def get_hold_for_buyer(self, *, tx, hold_id, buyer_id):
        hold_key, buyer_key = db_id(hold_id), db_id(buyer_id)
        if hold_key is None or buyer_key is None:
            return None
        return _hold(
            tx.fetch_one(
                f"SELECT {_HOLD_COLUMNS} FROM holds WHERE id = :id AND buyer_id = :buyer FOR UPDATE",
                {"id": hold_key, "buyer": buyer_key},
            )
        )

    def convert_hold(self, *, tx, hold_id, buyer_id, now):
        return _hold(
            tx.fetch_one(
                f"""
                UPDATE holds SET status = 'converted', terminal_at = :now
                WHERE id = :id AND buyer_id = :buyer AND status = 'active' AND expires_at > :now
                RETURNING {_HOLD_COLUMNS}
                """,
                {"id": db_id(hold_id), "buyer": db_id(buyer_id), "now": now},
            )
        )

    def release_hold(self, *, tx, hold_id, buyer_id, reason: HoldReleaseReason, now):
        released = tx.fetch_one(
            f"""
            UPDATE holds SET status = :status, terminal_at = :now
            WHERE id = :id AND buyer_id = :buyer AND status = 'active'
            RETURNING {_HOLD_COLUMNS}
            """,
            {
                "status": str(HoldReleaseReason(reason).status),
                "id": db_id(hold_id),
                "buyer": db_id(buyer_id),
                "now": now,
            },
        )
        if released is not None:
            return _hold(released)
        return self.get_hold_for_buyer(tx=tx, hold_id=hold_id, buyer_id=buyer_id)
