from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.orders.models import OrderSnapshot
    from app.purchase.ports import PostgresTransactionContext


class OrderSnapshotPort(Protocol):
    def create_order_snapshot(
        self,
        *,
        tx: PostgresTransactionContext,
        buyer_id: str,
        hold: object,
        quote_snapshot: object,
    ) -> OrderSnapshot: ...

    def get_for_buyer(
        self,
        *,
        tx: PostgresTransactionContext,
        buyer_id: str,
        order_id: str,
    ) -> OrderSnapshot | None: ...

    def list_for_buyer(
        self,
        *,
        tx: PostgresTransactionContext,
        buyer_id: str,
        limit: int,
        cursor: str | None = None,
    ) -> Sequence[OrderSnapshot]: ...
