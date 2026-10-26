"""Small PostgreSQL/simulated adapters used only by the purchase coordinator."""

from __future__ import annotations

from datetime import datetime

from app.db.transaction import db_id
from app.purchase.models import PaymentResult


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
