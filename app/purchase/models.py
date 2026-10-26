from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.audit.models import PurchaseAttemptAudit
    from app.inventory.models import Hold
    from app.orders.models import OrderSnapshot


class PurchaseOutcome(StrEnum):
    SUCCESS = "success"
    HOLD_CREATED = "hold_created"
    PAYMENT_FAILED = "payment_failed"
    INVALID_QUANTITY = "invalid_quantity"
    UNSUPPORTED_CURRENCY = "unsupported_currency"
    SOLD_OUT = "sold_out"
    HOLD_EXPIRED = "hold_expired"
    HOLD_NOT_FOUND = "hold_not_found"
    HOLD_TERMINAL = "hold_terminal"
    IDEMPOTENCY_KEY_REQUIRED = "idempotency_key_required"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"


@dataclass(frozen=True, slots=True)
class PurchaseRequest:
    """Buyer intent only; identity and pricing are resolved by server-owned ports."""

    event_id: str
    quantity: object
    currency: object
    request_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class PaymentRequest:
    hold_id: str
    request_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    """Immutable server-owned pricing result copied into the order."""

    event_id: str
    quantity: int
    currency: str
    exchange_rate: Decimal
    total_minor: int
    unit_price_minor: int | None = None
    snapshot_version: str = "quote-v1"


@dataclass(frozen=True, slots=True)
class PaymentResult:
    succeeded: bool
    reason_code: str = "PAYMENT_FAILED"


@dataclass(frozen=True, slots=True)
class CheckoutResult:
    outcome: PurchaseOutcome
    reason_code: str
    buyer_id: str
    hold: Hold | None
    quote: QuoteSnapshot | None
    audit: PurchaseAttemptAudit


@dataclass(frozen=True, slots=True)
class PurchaseResult:
    outcome: PurchaseOutcome
    reason_code: str
    buyer_id: str
    hold: Hold | None
    order: OrderSnapshot | None
    audit: PurchaseAttemptAudit


class IdempotencyDecision(StrEnum):
    NEW = "new"
    REPLAY = "replay"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    decision: IdempotencyDecision
    result: PurchaseResult | None = None
