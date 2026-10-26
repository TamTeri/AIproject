from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class HoldStatus(StrEnum):
    """Matches the holds.status CHECK constraint in migration 0004 exactly."""

    ACTIVE = "active"
    CONVERTED = "converted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PAYMENT_FAILED = "payment_failed"


class HoldReleaseReason(StrEnum):
    PAYMENT_FAILED = "payment_failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

    @property
    def status(self) -> HoldStatus:
        return HoldStatus(self.value)


@dataclass(frozen=True, slots=True)
class Hold:
    id: str
    buyer_id: str
    event_id: str
    quantity: int
    expires_at: datetime
    status: HoldStatus = HoldStatus.ACTIVE
    release_reason: HoldReleaseReason | None = None
    quote_snapshot: Any = None

    @property
    def terminal(self) -> bool:
        return self.status is not HoldStatus.ACTIVE
