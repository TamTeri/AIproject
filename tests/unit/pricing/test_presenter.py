"""The shared price-breakdown presenter and the removal of silent exponent defaults (pricing-014)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.pricing.calculator import BASE_CURRENCY
from app.pricing.config import PricingPolicy, temporary_local_policy
from app.pricing.presenter import present_breakdown
from app.purchase.models import QuoteSnapshot

pytestmark = [pytest.mark.requirement("pricing-014", "system-016")]


def test_jpy_breakdown_with_base_list_price():
    shown = present_breakdown(
        currency="JPY",
        exponent=0,
        total_minor=4050,
        discount_minor=450,
        subtotal_minor=4500,
        unit_price_minor=3000,
        base=BASE_CURRENCY,
    )
    assert (shown.subtotal, shown.discount, shown.total) == ("4,500 JPY", "450 JPY", "4,050 JPY")
    assert shown.discount_applied is True
    assert shown.list_price == "30.00 USD"


def test_subtotal_falls_back_to_total_plus_discount_and_list_price_may_be_absent():
    shown = present_breakdown(
        currency="EUR",
        exponent=2,
        total_minor=4140,
        discount_minor=460,
        subtotal_minor=None,
        unit_price_minor=None,
        base=BASE_CURRENCY,
    )
    assert shown.subtotal == "46.00 EUR"
    assert shown.list_price == ""


def test_quote_snapshot_requires_exponent():
    base = dict(event_id="1", quantity=1, currency="USD", exchange_rate=Decimal(1), total_minor=1)
    with pytest.raises(TypeError):
        QuoteSnapshot(**base)  # type: ignore[call-arg]
    assert QuoteSnapshot(**base, currency_exponent=0).currency_exponent == 0


def test_snapshot_json_without_exponent_is_rejected():
    data = QuoteSnapshot(
        event_id="1",
        quantity=1,
        currency="JPY",
        exchange_rate=Decimal(150),
        total_minor=4500,
        currency_exponent=0,
    ).to_json()
    assert QuoteSnapshot.from_json(data).currency_exponent == 0
    del data["currency_exponent"]
    with pytest.raises(KeyError):
        QuoteSnapshot.from_json(data)


def test_pricing_policy_requires_currency_and_exponent():
    with pytest.raises(TypeError):
        PricingPolicy(revision="r", discount_percent="10", eligibility_domain="usf.edu")  # type: ignore[call-arg]
    assert temporary_local_policy().currency_exponent == 2
