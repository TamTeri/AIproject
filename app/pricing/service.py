"""QuoteService: turns server-owned facts into an immutable QuoteSnapshot.

Implements the purchase ``QuotePort``. All facts (buyer email, event price,
currency, rate) come from the repository port, never from the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from app.pricing.calculator import calculate_price
from app.pricing.config import PricingPolicy
from app.pricing.eligibility import EventFacts, IdentityFacts, evaluate_student_eligibility
from app.purchase.models import QuoteSnapshot


class QuoteUnavailable(LookupError):
    """Event, buyer or currency could not be priced. Coordinator validates first."""


@dataclass(frozen=True, slots=True)
class CurrencyInfo:
    code: str
    exponent: int
    rate: Decimal


@dataclass(frozen=True, slots=True)
class EventPrice:
    event_id: str
    base_price_minor: int
    host_type: str | None = None


class PricingRepository(Protocol):
    def buyer_email(self, tx: Any, buyer_id: str) -> str | None: ...

    def event_price(self, tx: Any, event_id: str) -> EventPrice | None: ...

    def currency(self, tx: Any, code: str) -> CurrencyInfo | None: ...

    def enabled_currencies(self, tx: Any) -> list[CurrencyInfo]: ...


class QuoteService:
    def __init__(self, *, repository: PricingRepository, policy: PricingPolicy) -> None:
        self._repository = repository
        self._policy = policy

    @property
    def policy(self) -> PricingPolicy:
        return self._policy

    def supported_currencies(self, tx: Any) -> set[str]:
        return {c.code for c in self._repository.enabled_currencies(tx)}

    def quote(self, *, tx: Any, buyer_id: str, event_id: str, quantity: int, currency: str) -> QuoteSnapshot:
        email = self._repository.buyer_email(tx, buyer_id)
        event = self._repository.event_price(tx, event_id)
        info = self._repository.currency(tx, currency)
        if email is None or event is None or info is None:
            raise QuoteUnavailable("quote inputs are unavailable")

        decision = evaluate_student_eligibility(
            IdentityFacts(email=email, identity_id=buyer_id),
            EventFacts(event_id=event_id, classification=event.host_type),
            self._policy,
        )
        price = calculate_price(
            base_price_minor=event.base_price_minor,
            quantity=quantity,
            discount_eligible=decision.eligible,
            currency=info.code,
            exchange_rate=info.rate,
            currency_exponent=info.exponent,
            policy=self._policy,
        )
        return QuoteSnapshot(
            event_id=event_id,
            quantity=quantity,
            currency=info.code,
            exchange_rate=info.rate,
            total_minor=price.total_minor,
            unit_price_minor=event.base_price_minor,
            currency_exponent=info.exponent,
            subtotal_minor=price.subtotal_minor,
            discount_minor=price.discount_minor,
            discount_percent=price.discount_percent,
            discount_reason=decision.reason,
            policy_revision=decision.policy_revision,
        )


__all__ = ["CurrencyInfo", "EventPrice", "PricingRepository", "QuoteService", "QuoteUnavailable"]
