"""The one place EventHub computes money (pricing-001/002, Call 4 rule).

One function takes base price, quantity, discount eligibility and target
currency (with its configured rate) and returns the amount. No route, template
or other module computes a price.

Money representation (docs/adr/ADR-005-money-representation.md):
- amounts are integers in the currency's minor unit (cents);
- exchange rates are exact Decimals ("1 USD = rate units of target");
- order of operations: base x quantity -> discount (in USD) -> convert ->
  round once, half-up, to the target currency's minor unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.pricing.config import PricingPolicy

BASE_EXPONENT = 2  # USD cents
MAX_QUANTITY = 1_000


class PriceError(ValueError):
    """Raised when price inputs are invalid. Callers validate first."""


@dataclass(frozen=True, slots=True)
class PriceBreakdown:
    currency: str
    exponent: int
    quantity: int
    unit_price_minor_base: int
    exchange_rate: Decimal
    discount_percent: Decimal
    discount_applied: bool
    subtotal_minor: int  # target currency, before discount
    discount_minor: int  # target currency; subtotal - discount == total exactly
    total_minor: int  # target currency, what the buyer pays


def _round_to_minor(amount_base_minor: Decimal, rate: Decimal, exponent: int) -> int:
    scaled = amount_base_minor * rate * (Decimal(10) ** (exponent - BASE_EXPONENT))
    return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def calculate_price(
    *,
    base_price_minor: int,
    quantity: int,
    discount_eligible: bool,
    currency: str,
    exchange_rate: Decimal,
    currency_exponent: int,
    policy: PricingPolicy,
) -> PriceBreakdown:
    if isinstance(base_price_minor, bool) or not isinstance(base_price_minor, int):
        raise PriceError("base price must be an integer number of cents")
    if base_price_minor < 0:
        raise PriceError("base price must not be negative")
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise PriceError("quantity must be an integer")
    if not 1 <= quantity <= MAX_QUANTITY:
        raise PriceError(f"quantity must be between 1 and {MAX_QUANTITY}")
    if not isinstance(exchange_rate, Decimal) or not exchange_rate.is_finite():
        raise PriceError("exchange rate must be an exact Decimal")
    if exchange_rate <= 0:
        raise PriceError("exchange rate must be positive")
    if not isinstance(currency_exponent, int) or not 0 <= currency_exponent <= 4:
        raise PriceError("currency exponent must be between 0 and 4")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise PriceError("currency must be a three-letter code")

    percent = Decimal(policy.discount_percent) if discount_eligible else Decimal(0)
    subtotal_base = Decimal(base_price_minor * quantity)
    discounted_base = subtotal_base - subtotal_base * percent / Decimal(100)

    subtotal_minor = _round_to_minor(subtotal_base, exchange_rate, currency_exponent)
    total_minor = _round_to_minor(discounted_base, exchange_rate, currency_exponent)

    return PriceBreakdown(
        currency=currency.upper(),
        exponent=currency_exponent,
        quantity=quantity,
        unit_price_minor_base=base_price_minor,
        exchange_rate=exchange_rate,
        discount_percent=percent,
        discount_applied=percent > 0,
        subtotal_minor=subtotal_minor,
        discount_minor=subtotal_minor - total_minor,
        total_minor=total_minor,
    )


def format_minor(amount_minor: int, currency: str, exponent: int) -> str:
    """Display helper: 2500, "USD", 2 -> "25.00 USD". Formatting only, no math."""
    value = Decimal(amount_minor).scaleb(-exponent)
    return f"{value:,.{exponent}f} {currency}"


def format_rate(rate: Decimal) -> str:
    """Display helper: Decimal("0.92000000") -> "0.92", Decimal("150") -> "150"."""
    text = f"{Decimal(rate).normalize():f}"
    return text


__all__ = ["MAX_QUANTITY", "PriceBreakdown", "PriceError", "calculate_price", "format_minor", "format_rate"]
