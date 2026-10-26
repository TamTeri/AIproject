from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    id: str
    buyer_id: str
    event_id: str
    hold_id: str
    quantity: int
    currency: str
    exchange_rate: Decimal
    total_minor: int
    quote_snapshot: Any
