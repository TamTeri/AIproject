"""Order view across exponents (pricing-014, system-016): yen must not be shown as 45 yen."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.orders.service import to_view

pytestmark = [pytest.mark.requirement("pricing-014", "system-016")]


def row(snapshot):
    return {
        "id": 7,
        "title": "T",
        "artist": "A",
        "venue": "V",
        "starts_at": datetime(2027, 1, 1, tzinfo=UTC),
        "quantity": 1,
        "currency": "JPY",
        "rate_applied": Decimal("150.00000000"),
        "discount_minor": 450,
        "total_minor": 4050,
        "quote_snapshot": snapshot,
        "created_at": datetime(2026, 11, 1, tzinfo=UTC),
    }


def test_jpy_order_shows_whole_yen_and_usd_list_price():
    view = to_view(row({"currency_exponent": 0, "subtotal_minor": 4500, "unit_price_minor": 3000}))
    assert (view.subtotal, view.discount, view.total) == ("4,500 JPY", "450 JPY", "4,050 JPY")
    assert view.list_price == "30.00 USD"


@pytest.mark.parametrize("snapshot", [{}, None, {"subtotal_minor": 4500}])
def test_snapshot_without_exponent_raises(snapshot):
    with pytest.raises(KeyError):
        to_view(row(snapshot))
