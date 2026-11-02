"""Small PostgreSQL/simulated adapters used only by the purchase coordinator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

from app.db.transaction import db_id
from app.purchase.models import IdempotencyClaim, IdempotencyDecision, PaymentResult

# [TEMPORARY_MVP_DEFAULT] how long a one-time form key is remembered. Longer than
# the 12-hour maximum session, so a page cannot outlive its key's record.
IDEMPOTENCY_RETENTION_HOURS = 24


class SessionBuyer:
    """Identity port: the buyer comes from the server-side session, never the form."""

    def __init__(self, buyer_id: str) -> None:
        self._buyer_id = str(buyer_id)

    def current_buyer_id(self, tx) -> str:
        return self._buyer_id


class PostgresClock:
    """Database time at the mutation point, not the web server's clock."""

    def now(self, tx) -> datetime:
        return tx.fetch_one("SELECT CURRENT_TIMESTAMP AS now")["now"]


class PostgresPurchasableEvents:
    def lock_event(self, tx, event_id: str) -> bool:
        key = db_id(event_id)
        if key is None:
            return False
        row = tx.fetch_one(
            "SELECT id FROM events WHERE id = :id AND status = 'active' FOR UPDATE", {"id": key}
        )
        return row is not None

    def event_exists(self, tx, event_id: str) -> bool:
        key = db_id(event_id)
        if key is None:
            return False
        return tx.fetch_one("SELECT id FROM events WHERE id = :id", {"id": key}) is not None

    def sales_closed(self, tx, event_id: str, now: datetime) -> bool:
        """purchase-018 [TEMPORARY_MVP_DEFAULT]: sales close at the start time."""
        row = tx.fetch_one(
            "SELECT starts_at <= :now AS closed FROM events WHERE id = :id",
            {"id": db_id(event_id), "now": now},
        )
        return bool(row and row["closed"])


class PostgresIdempotency:
    """purchase-014: one-time form keys in ``idempotency_records``.

    The INSERT runs inside the purchase transaction. If a second request with
    the same key arrives while the first is still running, PostgreSQL makes it
    wait on the primary key until the first commits; ON CONFLICT DO NOTHING then
    returns no row and we read the stored result. If the first rolls back, its
    row disappears and the second proceeds as new.
    """

    def claim(self, *, tx, buyer_id: str, key: str, request_hash: str) -> IdempotencyClaim:
        # Housekeeping: this buyer's keys older than the retention window are no longer needed.
        tx.execute(
            "DELETE FROM idempotency_records WHERE buyer_id = :buyer AND expires_at <= CURRENT_TIMESTAMP",
            {"buyer": db_id(buyer_id)},
        )
        inserted = tx.fetch_one(
            """
            INSERT INTO idempotency_records (buyer_id, idempotency_key, request_hash, state,
                                             created_at, expires_at)
            VALUES (:buyer, :key, :hash, 'in_progress', CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP + make_interval(hours => :hours))
            ON CONFLICT (buyer_id, idempotency_key) DO NOTHING
            RETURNING buyer_id
            """,
            {
                "buyer": db_id(buyer_id),
                "key": key,
                "hash": request_hash,
                "hours": IDEMPOTENCY_RETENTION_HOURS,
            },
        )
        if inserted is not None:
            return IdempotencyClaim(IdempotencyDecision.NEW)
        existing = tx.fetch_one(
            """
            SELECT request_hash, state, outcome_payload FROM idempotency_records
            WHERE buyer_id = :buyer AND idempotency_key = :key
            """,
            {"buyer": db_id(buyer_id), "key": key},
        )
        if existing is None or existing["request_hash"] != request_hash or existing["state"] != "completed":
            return IdempotencyClaim(IdempotencyDecision.CONFLICT)
        payload = existing["outcome_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return IdempotencyClaim(IdempotencyDecision.REPLAY, dict(payload or {}))

    def release(self, *, tx, buyer_id: str, key: str) -> None:
        tx.execute(
            """
            DELETE FROM idempotency_records
            WHERE buyer_id = :buyer AND idempotency_key = :key AND state = 'in_progress'
            """,
            {"buyer": db_id(buyer_id), "key": key},
        )

    def complete(self, *, tx, buyer_id: str, key: str, payload: Mapping[str, object]) -> None:
        tx.execute(
            """
            UPDATE idempotency_records
            SET state = 'completed', completed_at = CURRENT_TIMESTAMP,
                outcome_payload = CAST(:payload AS JSONB)
            WHERE buyer_id = :buyer AND idempotency_key = :key AND state = 'in_progress'
            """,
            {"buyer": db_id(buyer_id), "key": key, "payload": json.dumps(dict(payload))},
        )


class PostgresRequestRate:
    """purchase-015: a fixed-window request counter per account.

    One row per buyer in ``purchase_rate_windows``. The upsert locks that row,
    so one buyer's purchase requests are counted one at a time, across every
    web worker. A new window starts when the old one is ``window_seconds`` old.
    """

    def count_request(self, *, tx, buyer_id: str, now: datetime, window_seconds: int) -> int:
        row = tx.fetch_one(
            """
            INSERT INTO purchase_rate_windows AS w (buyer_id, window_started_at, request_count)
            VALUES (:buyer, :now, 1)
            ON CONFLICT (buyer_id) DO UPDATE SET
                request_count = CASE WHEN w.window_started_at <= :now - make_interval(secs => :window)
                                     THEN 1 ELSE w.request_count + 1 END,
                window_started_at = CASE WHEN w.window_started_at <= :now - make_interval(secs => :window)
                                         THEN :now ELSE w.window_started_at END
            RETURNING request_count
            """,
            {"buyer": db_id(buyer_id), "now": now, "window": window_seconds},
        )
        return int(row["request_count"])


class PostgresPurchaseLimits:
    def committed_quantity(self, tx, *, buyer_id: str, event_id: str) -> int:
        row = tx.fetch_one(
            """
            SELECT COALESCE((SELECT SUM(quantity) FROM orders
                             WHERE buyer_id = :buyer AND event_id = :event), 0)
                 + COALESCE((SELECT SUM(quantity) FROM holds
                             WHERE buyer_id = :buyer AND event_id = :event
                               AND status = 'active' AND expires_at > CURRENT_TIMESTAMP), 0)
                   AS committed
            """,
            {"buyer": db_id(buyer_id), "event": db_id(event_id)},
        )
        return int(row["committed"])


class SimulatedPayments:
    """purchase-004: no external payment provider in version one.

    The checkout page offers a simulated card that approves or declines so
    the failure path can be demonstrated and tested.
    """

    def simulate(self, *, tx, buyer_id, hold, quote_snapshot, payment_choice: str = "approve"):
        if payment_choice == "decline":
            return PaymentResult(succeeded=False, reason_code="card_declined")
        return PaymentResult(succeeded=True, reason_code="OK")
