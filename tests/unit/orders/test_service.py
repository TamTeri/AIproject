"""Order history and confirmation view (orders-001..004, identity-010)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.orders.service import OrderHistoryService


def row(order_id: int, buyer: str) -> dict:
    return {
        "id": order_id,
        "buyer": buyer,
        "title": "Fall Jazz Night",
        "artist": "Bulls Jazz",
        "venue": "Theatre 1",
        "starts_at": datetime(2026, 11, 8, tzinfo=UTC),
        "quantity": 2,
        "currency": "EUR",
        "rate_applied": Decimal("0.92000000"),
        "discount_minor": 460,
        "total_minor": 4140,
        "quote_snapshot": {"currency_exponent": 2, "subtotal_minor": 4600},
        "created_at": datetime(2026, 11, 1, tzinfo=UTC),
    }


class FakeOrders:
    def __init__(self) -> None:
        self.rows = [row(1, "a"), row(2, "b")]

    def list_for_buyer(self, buyer_id, *, limit):
        return [r for r in self.rows if r["buyer"] == buyer_id][:limit]

    def get_for_buyer(self, buyer_id, order_id):
        return next((r for r in self.rows if r["buyer"] == buyer_id and str(r["id"]) == order_id), None)


def test_confirmation_shows_event_quantity_currency_rate_and_total():
    view = OrderHistoryService(repository=FakeOrders()).get_for_buyer(buyer_id="a", order_id="1")
    assert view.event_title == "Fall Jazz Night"
    assert view.quantity == 2
    assert view.currency == "EUR"
    assert view.exchange_rate == Decimal("0.92")
    assert (view.subtotal, view.discount, view.total) == ("46.00 EUR", "4.60 EUR", "41.40 EUR")
    assert view.discount_applied is True


def test_buyer_sees_only_their_own_orders():
    service = OrderHistoryService(repository=FakeOrders())
    assert [o.id for o in service.list_for_buyer(buyer_id="a")] == ["1"]
    assert service.get_for_buyer(buyer_id="a", order_id="2") is None


def test_bad_order_ids_are_not_found():
    service = OrderHistoryService(repository=FakeOrders())
    for bad in ("", "abc", "1;DROP", "9" * 40):
        assert service.get_for_buyer(buyer_id="a", order_id=bad) is None
