"""Every enabled seeded currency, end to end against PostgreSQL (pricing-014, system-016).

NOT EXECUTED on the machine that wrote it (no PostgreSQL there); it runs in CI
or with EVENTHUB_TEST_DATABASE_URL set. One 30.00 USD ticket, no discount, is
bought in each currency. The expected minor amounts and texts are hand-derived
literals; the 4,500 yen row is the Call 6 example ("45 yen" must never appear).
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.purchase.models import PurchaseOutcome
from app.wiring import build_services

pytestmark = [pytest.mark.postgres, pytest.mark.requirement("pricing-014", "system-016")]

SEED = json.loads((Path(__file__).parents[2] / "seed" / "catalog.json").read_text(encoding="utf-8"))
ENABLED = [c["code"] for c in SEED["currencies"] if c["enabled"]]

# 30.00 USD x seeded rate, rounded half-up to the currency's minor unit.
EXPECTED = {
    "USD": (3000, "30.00 USD"),
    "EUR": (2760, "27.60 EUR"),  # x 0.92
    "GBP": (2370, "23.70 GBP"),  # x 0.79
    "CAD": (4140, "41.40 CAD"),  # x 1.38
    "JPY": (4500, "4,500 JPY"),  # x 150, zero-decimal
}


def test_every_enabled_seed_currency_has_a_hand_derived_expectation():
    assert set(ENABLED) == set(EXPECTED)
    assert "JPY" in ENABLED


@pytest.mark.parametrize("code", ENABLED)
def test_purchase_in_each_enabled_currency(seeded_database, code):
    services = build_services(seeded_database, environment="test")
    expected_minor, expected_text = EXPECTED[code]

    with seeded_database.engine.begin() as connection:
        event_id = str(
            connection.execute(
                text(
                    """
                    INSERT INTO events (catalog_key, title, artist, venue, starts_at, host_type,
                                        base_price_minor, capacity)
                    VALUES (:key, 'Money', 'Money Band', 'Hall', CURRENT_TIMESTAMP + INTERVAL '30 days',
                            'usf', 3000, 5)
                    RETURNING id
                    """
                ),
                {"key": f"money-{uuid4().hex}"},
            ).scalar_one()
        )
    buyer = services.identity.register(
        name="Money Buyer", email="money@example.com", password="password-123"
    ).account_id

    result = services.purchase.quick_buy(
        buyer_id=buyer, event_id=event_id, currency=code, idempotency_key=uuid4().hex
    )
    assert result.outcome is PurchaseOutcome.SUCCESS

    # 1. the database row
    with seeded_database.engine.connect() as connection:
        order = connection.execute(
            text("SELECT id, currency, total_minor FROM orders WHERE buyer_id = :b"), {"b": int(buyer)}
        ).one()
        audit = connection.execute(
            text(
                "SELECT currency_raw, outcome, order_id FROM purchase_attempts "
                "WHERE buyer_id = :b AND outcome = 'success'"
            ),
            {"b": int(buyer)},
        ).one()
    assert (order.currency, order.total_minor) == (code, expected_minor)

    # 2. the rendered order-detail text (what the page prints)
    view = services.orders.get_for_buyer(buyer_id=buyer, order_id=str(order.id))
    assert view.total == expected_text
    assert view.list_price == "30.00 USD"
    if code == "JPY":
        assert view.total != "45 JPY"

    # 3. the audit row
    assert tuple(audit) == (code, "success", order.id)
