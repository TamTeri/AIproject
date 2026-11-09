"""The one price-breakdown view (pricing-014): order pages and checkout review both use it."""

from __future__ import annotations

from dataclasses import dataclass

from app.pricing.calculator import Currency, format_minor


@dataclass(frozen=True, slots=True)
class BreakdownDisplay:
    subtotal: str
    discount: str
    total: str
    discount_applied: bool
    list_price: str  # base-currency ticket price, a reference only; "" when unknown


def present_breakdown(
    *,
    currency: str,
    exponent: int,
    total_minor: int,
    discount_minor: int,
    subtotal_minor: int | None,
    unit_price_minor: int | None,
    base: Currency,
) -> BreakdownDisplay:
    subtotal = subtotal_minor if subtotal_minor is not None else total_minor + discount_minor
    return BreakdownDisplay(
        subtotal=format_minor(subtotal, currency, exponent),
        discount=format_minor(discount_minor, currency, exponent),
        total=format_minor(total_minor, currency, exponent),
        discount_applied=discount_minor > 0,
        list_price=format_minor(unit_price_minor, base.code, base.exponent)
        if unit_price_minor is not None
        else "",
    )
