"""PostgreSQL adapter for pricing facts: buyer email, event base price, and
enabled currencies with their configured (not live) exchange rates."""

from __future__ import annotations

from decimal import Decimal

from app.db.transaction import db_id
from app.pricing.service import CurrencyInfo, EventPrice

_CURRENCIES = """
    SELECT c.code, c.minor_unit, r.rate
    FROM currencies c JOIN exchange_rates r ON r.currency_code = c.code
    WHERE c.enabled
"""


def _currency(row: dict) -> CurrencyInfo:
    return CurrencyInfo(code=row["code"], exponent=int(row["minor_unit"]), rate=Decimal(str(row["rate"])))


class PostgresPricingRepository:
    def buyer_email(self, tx, buyer_id: str) -> str | None:
        row = tx.fetch_one("SELECT normalized_email FROM accounts WHERE id = :id", {"id": db_id(buyer_id)})
        return row["normalized_email"] if row else None

    def event_price(self, tx, event_id: str) -> EventPrice | None:
        row = tx.fetch_one(
            "SELECT id, base_price_minor, host_type FROM events WHERE id = :id AND status = 'active'",
            {"id": db_id(event_id)},
        )
        if row is None:
            return None
        return EventPrice(str(row["id"]), int(row["base_price_minor"]), row["host_type"])

    def currency(self, tx, code: str) -> CurrencyInfo | None:
        row = tx.fetch_one(_CURRENCIES + " AND c.code = :code", {"code": code})
        return _currency(row) if row else None

    def enabled_currencies(self, tx) -> list[CurrencyInfo]:
        return [_currency(r) for r in tx.fetch_all(_CURRENCIES + " ORDER BY c.code")]
