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
    """Specific result of one attempt. Stored as the audit ``reason_code``."""

    SUCCESS = "success"
    HOLD_CREATED = "hold_created"
    CANCELLED = "cancelled"
    PAYMENT_FAILED = "payment_failed"
    INVALID_QUANTITY = "invalid_quantity"
    UNSUPPORTED_CURRENCY = "unsupported_currency"
    EVENT_NOT_FOUND = "event_not_found"
    SOLD_OUT = "sold_out"
    LIMIT_EXCEEDED = "limit_exceeded"
    HOLD_EXPIRED = "hold_expired"
    HOLD_NOT_FOUND = "hold_not_found"
    HOLD_TERMINAL = "hold_terminal"
    INTERNAL_ERROR = "internal_error"
    IDEMPOTENCY_KEY_REQUIRED = "idempotency_key_required"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"


class AuditCategory(StrEnum):
    """The four values the purchase_attempts.outcome column accepts."""

    SUCCESS = "success"
    REJECTED = "rejected"
    FAILED = "failed"
    REPLAYED = "replayed"


_FAILED = {PurchaseOutcome.PAYMENT_FAILED, PurchaseOutcome.INTERNAL_ERROR}


def audit_category(outcome: PurchaseOutcome) -> AuditCategory:
    if outcome is PurchaseOutcome.SUCCESS:
        return AuditCategory.SUCCESS
    if outcome in _FAILED:
        return AuditCategory.FAILED
    return AuditCategory.REJECTED


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
    payment_choice: str = "approve"  # simulated card: "approve" or "decline"


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    """Immutable server-owned pricing result copied into the hold and order."""

    event_id: str
    quantity: int
    currency: str
    exchange_rate: Decimal
    total_minor: int
    unit_price_minor: int | None = None
    snapshot_version: str = "quote-v1"
    currency_exponent: int = 2
    subtotal_minor: int | None = None
    discount_minor: int = 0
    discount_percent: Decimal = Decimal(0)
    discount_reason: str = "not_evaluated"
    policy_revision: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "quantity": self.quantity,
            "currency": self.currency,
            "exchange_rate": str(self.exchange_rate),
            "total_minor": self.total_minor,
            "unit_price_minor": self.unit_price_minor,
            "snapshot_version": self.snapshot_version,
            "currency_exponent": self.currency_exponent,
            "subtotal_minor": self.subtotal_minor,
            "discount_minor": self.discount_minor,
            "discount_percent": str(self.discount_percent),
            "discount_reason": self.discount_reason,
            "policy_revision": self.policy_revision,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> QuoteSnapshot:
        return cls(
            event_id=str(data["event_id"]),
            quantity=int(data["quantity"]),
            currency=str(data["currency"]),
            exchange_rate=Decimal(str(data["exchange_rate"])),
            total_minor=int(data["total_minor"]),
            unit_price_minor=data.get("unit_price_minor"),
            snapshot_version=str(data.get("snapshot_version", "quote-v1")),
            currency_exponent=int(data.get("currency_exponent", 2)),
            subtotal_minor=data.get("subtotal_minor"),
            discount_minor=int(data.get("discount_minor", 0)),
            discount_percent=Decimal(str(data.get("discount_percent", "0"))),
            discount_reason=str(data.get("discount_reason", "not_evaluated")),
            policy_revision=data.get("policy_revision"),
        )


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
    audit: PurchaseAttemptAudit | None


@dataclass(frozen=True, slots=True)
class PurchasePolicy:
    """[TEMPORARY_MVP_DEFAULT] purchase rules from seed/config.example.json."""

    hold_minutes: int = 10
    per_account_event_limit: int = 4


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
