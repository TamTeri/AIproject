from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re


_CODE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_MAX_ID = 128
_MAX_CODE = 64
_MAX_OUTCOME = 32
_MAX_CURRENCY = 16


def _bounded(value: str | None, *, name: str, limit: int, required: bool = False) -> None:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return
    if not isinstance(value, str) or not value or len(value) > limit or not _CODE.fullmatch(value):
        raise ValueError(f"{name} is not bounded")


@dataclass(frozen=True, slots=True)
class PurchaseAttemptAudit:
    attempt_id: str
    submitted_at: datetime
    buyer_id: str | None
    event_id: str | None
    quantity: int | None
    currency: str | None
    outcome: str
    reason_code: str
    request_id: str | None = None
    idempotency_key: str | None = None
    hold_id: str | None = None
    order_id: str | None = None

    def __post_init__(self) -> None:
        _bounded(self.attempt_id, name="attempt_id", limit=_MAX_ID, required=True)
        _bounded(self.buyer_id, name="buyer_id", limit=_MAX_ID)
        _bounded(self.event_id, name="event_id", limit=_MAX_ID)
        _bounded(self.request_id, name="request_id", limit=_MAX_ID)
        _bounded(self.idempotency_key, name="idempotency_key", limit=_MAX_ID)
        _bounded(self.hold_id, name="hold_id", limit=_MAX_ID)
        _bounded(self.order_id, name="order_id", limit=_MAX_ID)
        _bounded(self.outcome, name="outcome", limit=_MAX_OUTCOME, required=True)
        _bounded(self.reason_code, name="reason_code", limit=_MAX_CODE, required=True)
        if self.currency is not None and (
            not isinstance(self.currency, str)
            or not self.currency
            or len(self.currency) > _MAX_CURRENCY
            or not self.currency.isascii()
            or any(character.isspace() for character in self.currency)
        ):
            raise ValueError("currency is not bounded")
        if self.quantity is not None and (
            not isinstance(self.quantity, int) or isinstance(self.quantity, bool) or not 0 <= self.quantity <= 1_000_000
        ):
            raise ValueError("quantity is not bounded")
        if self.submitted_at.tzinfo is None or self.submitted_at.utcoffset() is None:
            raise ValueError("submitted_at must be timezone-aware")
