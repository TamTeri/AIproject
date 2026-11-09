"""Order history and confirmation pages (orders-001..004, identity-010).

Buyers only ever see their own orders: the buyer id is part of every lookup,
so another buyer's order id simply returns "not found".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.pricing.calculator import BASE_CURRENCY, format_rate
from app.pricing.presenter import present_breakdown


@dataclass(frozen=True)
class OrderView:
    id: str
    event_title: str
    artist: str
    venue: str
    starts_at: datetime
    quantity: int
    currency: str
    exchange_rate: Decimal
    exchange_rate_display: str
    subtotal: str
    discount: str
    discount_applied: bool
    total: str
    created_at: datetime
    list_price: str = ""  # orders-006: the USD ticket price, shown as a reference only


class OrderReadRepository(Protocol):
    def list_for_buyer(self, buyer_id: str, *, limit: int) -> list[dict]: ...

    def get_for_buyer(self, buyer_id: str, order_id: str) -> dict | None: ...


def to_view(row: dict) -> OrderView:
    snapshot = row.get("quote_snapshot") or {}
    exponent = int(snapshot["currency_exponent"])
    currency = row["currency"]
    total = int(row["total_minor"])
    discount = int(row.get("discount_minor") or 0)
    shown = present_breakdown(
        currency=currency,
        exponent=exponent,
        total_minor=total,
        discount_minor=discount,
        subtotal_minor=snapshot.get("subtotal_minor"),
        unit_price_minor=snapshot.get("unit_price_minor"),
        base=BASE_CURRENCY,
    )
    return OrderView(
        id=str(row["id"]),
        event_title=row["title"],
        artist=row["artist"],
        venue=row["venue"],
        starts_at=row["starts_at"],
        quantity=int(row["quantity"]),
        currency=currency,
        exchange_rate=Decimal(str(row["rate_applied"])),
        exchange_rate_display=format_rate(Decimal(str(row["rate_applied"]))),
        subtotal=shown.subtotal,
        discount=shown.discount,
        discount_applied=shown.discount_applied,
        total=shown.total,
        created_at=row["created_at"],
        list_price=shown.list_price,
    )


class OrderHistoryService:
    def __init__(self, *, repository: OrderReadRepository, page_size: int = 100) -> None:
        self._repository = repository
        self._page_size = page_size

    def list_for_buyer(self, *, buyer_id: str) -> list[OrderView]:
        return [to_view(r) for r in self._repository.list_for_buyer(buyer_id, limit=self._page_size)]

    def get_for_buyer(self, *, buyer_id: str, order_id: str) -> OrderView | None:
        order_id = str(order_id or "").strip()
        if not (order_id.isascii() and order_id.isdigit()) or len(order_id) > 18:
            return None
        row = self._repository.get_for_buyer(buyer_id, order_id)
        return to_view(row) if row else None


__all__ = ["OrderHistoryService", "OrderReadRepository", "OrderView", "to_view"]
