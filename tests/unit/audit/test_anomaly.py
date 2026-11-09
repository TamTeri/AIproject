"""audit-009: flag orders whose price is far outside the event's price range (the 1% incident)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.audit.anomaly import Finding, find_anomalies, is_out_of_range, notify, usd_per_ticket_minor

pytestmark = pytest.mark.requirement("audit-009")


def test_incident_one_percent_of_price_is_flagged():
    assert is_out_of_range(Decimal(20), 2000)


def test_normal_price_and_discounted_price_pass():
    assert not is_out_of_range(Decimal(2000), 2000)
    assert not is_out_of_range(Decimal(1800), 2000)  # 10% discount


@pytest.mark.parametrize(
    ("usd", "flagged"),
    [(999, True), (1000, False), (4000, False), (4001, True)],
)
def test_boundaries_50_and_200_percent_are_inclusive_of_the_normal_band(usd, flagged):
    assert is_out_of_range(Decimal(usd), 2000) is flagged


def test_free_event_is_fine_when_free_but_flagged_when_charged():
    assert not is_out_of_range(Decimal(0), 0)
    assert is_out_of_range(Decimal(500), 0)


def test_legitimate_jpy_order_is_not_a_false_alarm():
    # 20.00 USD at 150 JPY per USD = 3000 yen (exponent 0), 2 tickets = 6000 yen
    usd = usd_per_ticket_minor(total_minor=6000, quantity=2, rate=Decimal(150), exponent=0)
    assert usd == Decimal(2000)
    assert not is_out_of_range(usd, 2000)


def test_jpy_charged_one_percent_is_flagged():
    usd = usd_per_ticket_minor(total_minor=30, quantity=1, rate=Decimal(150), exponent=0)
    assert is_out_of_range(usd, 2000)


class FakeTx:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""

    def fetch_all(self, statement, parameters=None):
        self.sql = statement
        return self.rows


def row(order_id, total, qty=1, rate="1", exp=2, currency="USD", base=2000):
    return {
        "order_id": order_id,
        "event_id": 7,
        "currency": currency,
        "total_minor": total,
        "quantity": qty,
        "rate_applied": Decimal(rate),
        "exponent": exp,
        "base_price_minor": base,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }


def test_find_anomalies_returns_only_flagged_orders_without_pii():
    tx = FakeTx([row(1, 2000), row(2, 20), row(3, 3000, rate="150", exp=0, currency="JPY")])
    findings = find_anomalies(tx)
    assert [f.order_id for f in findings] == ["2"]
    assert findings[0].ratio == Decimal("0.01")
    assert set(findings[0].__dataclass_fields__) == {
        "order_id",
        "event_id",
        "currency",
        "ratio",
        "created_at",
    }
    assert "email" not in tx.sql.lower() and "accounts" not in tx.sql.lower()


def test_notify_logs_at_error_without_pii(caplog):
    finding = Finding("2", "7", "USD", Decimal("0.01"), datetime(2026, 1, 1, tzinfo=UTC))
    with caplog.at_level(logging.ERROR, logger="eventhub.order_watch"):
        notify([finding])
    assert any(r.levelno == logging.ERROR and "order 2" in r.getMessage() for r in caplog.records)
