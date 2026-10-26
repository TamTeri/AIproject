"""The single pricing function (pricing-001/002/003, ADR-005)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.pricing.calculator import PriceError, calculate_price, format_minor
from app.pricing.config import STUDENT_DISCOUNT_PERCENT_PLACEHOLDER, temporary_local_policy

POLICY = temporary_local_policy()


def price(**overrides):
    values = dict(
        base_price_minor=2500,
        quantity=2,
        discount_eligible=False,
        currency="USD",
        exchange_rate=Decimal("1"),
        currency_exponent=2,
        policy=POLICY,
    )
    values.update(overrides)
    return calculate_price(**values)


def test_usd_without_discount_is_base_times_quantity():
    result = price()
    assert (result.subtotal_minor, result.discount_minor, result.total_minor) == (5000, 0, 5000)
    assert result.discount_applied is False


def test_student_discount_uses_the_flagged_placeholder_constant():
    result = price(discount_eligible=True)
    expected_discount = 5000 * STUDENT_DISCOUNT_PERCENT_PLACEHOLDER / 100
    assert result.discount_minor == int(expected_discount)
    assert result.total_minor == 5000 - int(expected_discount)
    assert result.discount_percent == STUDENT_DISCOUNT_PERCENT_PLACEHOLDER


def test_conversion_happens_after_discount():
    result = price(discount_eligible=True, currency="EUR", exchange_rate=Decimal("0.92"))
    # 50.00 USD -> 10% off = 45.00 USD -> x0.92 = 41.40 EUR
    assert result.total_minor == 4140
    assert result.subtotal_minor == 4600
    assert result.subtotal_minor - result.discount_minor == result.total_minor


def test_rounding_is_half_up_once_at_the_end():
    # 0.01 USD x 0.5 = 0.005 -> rounds half-up to 0.01
    result = price(base_price_minor=1, quantity=1, exchange_rate=Decimal("0.5"))
    assert result.total_minor == 1
    # 3 x 0.33 USD at rate 1.005 = 0.99495 -> 0.99
    result = price(base_price_minor=33, quantity=3, exchange_rate=Decimal("1.005"))
    assert result.total_minor == 99


def test_zero_decimal_currency_is_supported():
    result = price(
        base_price_minor=2500,
        quantity=1,
        currency="JPY",
        exchange_rate=Decimal("150.123"),
        currency_exponent=0,
    )
    assert result.total_minor == 3753  # 25 x 150.123 = 3753.075 -> 3753


def test_free_event_costs_nothing():
    assert price(base_price_minor=0).total_minor == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity": 0},
        {"quantity": -1},
        {"quantity": True},
        {"quantity": 1.5},
        {"base_price_minor": -1},
        {"base_price_minor": 10.5},
        {"exchange_rate": Decimal("0")},
        {"exchange_rate": Decimal("-1")},
        {"exchange_rate": Decimal("NaN")},
        {"exchange_rate": 0.92},
        {"currency": "EURO"},
        {"currency_exponent": 7},
    ],
)
def test_invalid_inputs_are_rejected(overrides):
    with pytest.raises(PriceError):
        price(**overrides)


def test_format_minor_is_display_only():
    assert format_minor(4140, "EUR", 2) == "41.40 EUR"
    assert format_minor(123456, "USD", 2) == "1,234.56 USD"
    assert format_minor(3753, "JPY", 0) == "3,753 JPY"


def test_format_rate_drops_database_padding_without_scientific_notation():
    from app.pricing.calculator import format_rate

    assert format_rate(Decimal("0.92000000")) == "0.92"
    assert format_rate(Decimal("1.00000000")) == "1"
    assert format_rate(Decimal("150.00000000")) == "150"
    assert format_rate(Decimal("1.38000000")) == "1.38"
