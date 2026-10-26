from __future__ import annotations

from datetime import datetime
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from app.inventory.models import Hold, HoldReleaseReason
    from app.purchase.ports import PostgresTransactionContext


class DatabaseTimePort(Protocol):
    """Reads database time at the mutation's transaction linearization point."""

    def now(self, tx: PostgresTransactionContext) -> datetime: ...


class AtomicInventoryPort(Protocol):
    """All methods are conditional, transaction-scoped, and never commit independently."""

    def allocate_hold(
        self,
        *,
        tx: PostgresTransactionContext,
        buyer_id: str,
        event_id: str,
        quantity: int,
        expires_at: datetime,
        quote_snapshot: object,
    ) -> Hold | None: ...

    def get_hold_for_buyer(
        self,
        *,
        tx: PostgresTransactionContext,
        hold_id: str,
        buyer_id: str,
    ) -> Hold | None: ...

    def convert_hold(
        self,
        *,
        tx: PostgresTransactionContext,
        hold_id: str,
        buyer_id: str,
        now: datetime,
    ) -> Hold | None: ...

    def release_hold(
        self,
        *,
        tx: PostgresTransactionContext,
        hold_id: str,
        buyer_id: str,
        reason: HoldReleaseReason,
        now: datetime,
    ) -> Hold | None: ...
