"""Hand-derived money totals per currency (pricing-014, system-016).

Every expected number below was worked out by hand from the ADR-005 rule
(base x qty -> discount in USD -> convert -> round once half-up), not by
calling the production formula. 10% is the placeholder student discount.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.pricing.calculator import calculate_price, format_minor
from app.pricing.config import temporary_local_policy

pytestmark = [pytest.mark.requirement("pricing-014", "system-016")]

POLICY = temporary_local_policy()


def price(base, qty, eligible, code, rate, exp):
    return calculate_price(
        base_price_minor=base,
        quantity=qty,
        discount_eligible=eligible,
        currency=code,
        exchange_rate=Decimal(rate),
        currency_exponent=exp,
        policy=POLICY,
    )


# (base cents, qty, discount, code, rate, exponent, subtotal, discount_minor, total)
CASES = [
    pytest.param(2500, 2, False, "USD", "1", 2, 5000, 0, 5000, id="usd-plain"),
    pytest.param(2500, 2, True, "USD", "1", 2, 5000, 500, 4500, id="usd-discount"),
    pytest.param(2500, 2, True, "EUR", "0.92", 2, 4600, 460, 4140, id="eur-discount"),
    pytest.param(2500, 1, False, "GBP", "0.79", 2, 1975, 0, 1975, id="gbp-plain"),
    # 22.50 x 0.79 = 17.775 -> 17.78 (half-up)
    pytest.param(2500, 1, True, "GBP", "0.79", 2, 1975, 197, 1778, id="gbp-discount-half-up"),
    pytest.param(2500, 1, True, "CAD", "1.38", 2, 3450, 345, 3105, id="cad-discount"),
    # 30.00 USD x 150 = 4,500 yen (the Call 6 example)
    pytest.param(3000, 1, False, "JPY", "150", 0, 4500, 0, 4500, id="jpy-4500"),
    pytest.param(3000, 1, True, "JPY", "150", 0, 4500, 450, 4050, id="jpy-4500-discount"),
    # half-up boundaries at exponent 0: 2.5 -> 3, 2.49 -> 2, 0.5 -> 1, 1.5 -> 2
    pytest.param(250, 1, False, "JPY", "1", 0, 3, 0, 3, id="jpy-2.5-up"),
    pytest.param(249, 1, False, "JPY", "1", 0, 2, 0, 2, id="jpy-2.49-down"),
    pytest.param(100, 1, False, "JPY", "0.5", 0, 1, 0, 1, id="jpy-0.5-up"),
    pytest.param(1, 1, False, "JPY", "150", 0, 2, 0, 2, id="jpy-1.5-up"),
    # discount THEN convert at exponent 0: 33.35 USD x 1.5 = 5002.5 -> 5003 subtotal;
    # 30.015 USD x 150 = 4502.25 -> 4502 (convert-round-then-discount would give 4503)
    pytest.param(3335, 1, True, "JPY", "150", 0, 5003, 501, 4502, id="jpy-discount-then-convert"),
    # exponent 3: 25.00 x 0.307 = 7.675
    pytest.param(2500, 1, False, "KWD", "0.307", 3, 7675, 0, 7675, id="exp3"),
    pytest.param(1, 1, False, "KWD", "0.05", 3, 1, 0, 1, id="exp3-half-up"),
    # exponent 4: 25.00 x 0.0245 = 0.6125
    pytest.param(2500, 1, False, "CLF", "0.0245", 4, 6125, 0, 6125, id="exp4"),
]


@pytest.mark.parametrize("base,qty,eligible,code,rate,exp,subtotal,discount,total", CASES)
def test_literal_totals(base, qty, eligible, code, rate, exp, subtotal, discount, total):
    result = price(base, qty, eligible, code, rate, exp)
    assert (result.subtotal_minor, result.discount_minor, result.total_minor) == (subtotal, discount, total)
    assert result.subtotal_minor - result.discount_minor == result.total_minor


@pytest.mark.parametrize(
    "minor,code,exp,text",
    [
        (4500, "JPY", 0, "4,500 JPY"),
        (3753, "JPY", 0, "3,753 JPY"),
        (4140, "EUR", 2, "41.40 EUR"),
        (7675, "KWD", 3, "7.675 KWD"),
        (6125, "CLF", 4, "0.6125 CLF"),
        (0, "JPY", 0, "0 JPY"),
    ],
)
def test_formatter_literals(minor, code, exp, text):
    assert format_minor(minor, code, exp) == text


def test_yen_is_never_shown_as_two_decimals():
    shown = format_minor(price(3000, 1, False, "JPY", "150", 0).total_minor, "JPY", 0)
    assert shown == "4,500 JPY"
    assert shown != "45 JPY" and "." not in shown


def test_missing_exponent_is_an_error_not_a_default():
    with pytest.raises(TypeError):
        calculate_price(  # type: ignore[call-arg]
            base_price_minor=100,
            quantity=1,
            discount_eligible=False,
            currency="USD",
            exchange_rate=Decimal(1),
            policy=POLICY,
        )
