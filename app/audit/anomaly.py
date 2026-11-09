"""Order-total anomaly check (audit-009): flag orders priced far from their event's base price.

Runs on the ``orders`` table only (no PII: no buyer, no email). Prices are compared in USD
so exchange rates do not false-alarm; the currency exponent handles JPY-style currencies.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.pricing.calculator import BASE_CURRENCY

log = logging.getLogger("eventhub.order_watch")

BASE_EXPONENT = BASE_CURRENCY.exponent  # USD cents (ADR-008: never write a literal 2)


@dataclass(frozen=True, slots=True)
class Finding:
    order_id: str
    event_id: str
    currency: str
    ratio: Decimal
    created_at: datetime


def is_out_of_range(usd_per_ticket_minor: Decimal | int, base_price_minor: int) -> bool:
    """True if the USD price per ticket is under 50% or over 200% of the event base price."""
    if base_price_minor <= 0:
        return usd_per_ticket_minor > 0  # a free event must stay free
    return 2 * usd_per_ticket_minor < base_price_minor or usd_per_ticket_minor > 2 * base_price_minor


def usd_per_ticket_minor(*, total_minor: int, quantity: int, rate: Decimal, exponent: int) -> Decimal:
    """Convert an order total (minor units of its currency; 1 USD = ``rate``) to USD cents per ticket."""
    return Decimal(total_minor) / quantity / (rate * Decimal(10) ** (exponent - BASE_EXPONENT))


_QUERY = """
    SELECT o.id AS order_id, o.event_id, o.currency_code AS currency, o.total_minor, o.quantity,
           o.rate_applied, c.minor_unit AS exponent, e.base_price_minor, o.created_at
    FROM orders o
    JOIN events e ON e.id = o.event_id
    JOIN currencies c ON c.code = o.currency_code
    WHERE o.created_at >= CURRENT_TIMESTAMP - make_interval(mins => :minutes)
    ORDER BY o.id
"""


def find_anomalies(tx: Any, *, since_minutes: int = 60) -> list[Finding]:
    """``tx`` is any object with ``fetch_all(sql, params)`` (an ``SqlTransaction``)."""
    findings = []
    for r in tx.fetch_all(_QUERY, {"minutes": since_minutes}):
        usd = usd_per_ticket_minor(
            total_minor=r["total_minor"],
            quantity=r["quantity"],
            rate=Decimal(str(r["rate_applied"])),
            exponent=int(r["exponent"]),
        )
        base = int(r["base_price_minor"])
        if is_out_of_range(usd, base):
            ratio = (usd / base).quantize(Decimal("0.0001")) if base else Decimal(0)
            findings.append(
                Finding(str(r["order_id"]), str(r["event_id"]), r["currency"], ratio, r["created_at"])
            )
    return findings


def notify(findings: Sequence[Finding]) -> None:
    """Default notifier: log at ERROR (the app has no SMTP configuration, so no email is sent)."""
    for f in findings:
        log.error(
            "order out of price range: order %s event %s %s ratio %s at %s",
            f.order_id,
            f.event_id,
            f.currency,
            f.ratio,
            f.created_at.isoformat(),
        )


Notifier = Callable[[Sequence[Finding]], None]
