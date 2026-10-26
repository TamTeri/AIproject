from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from app.audit.models import PurchaseAttemptAudit
    from app.purchase.ports import PostgresTransactionContext


class PurchaseAttemptAuditPort(Protocol):
    """Append-only purchase-attempt sink for the purchase transaction."""

    def append(self, *, tx: PostgresTransactionContext, record: PurchaseAttemptAudit) -> None: ...


class PurchaseAttemptAuditQueryPort(Protocol):
    def list_attempts(
        self,
        *,
        tx: PostgresTransactionContext,
        limit: int,
        cursor: str | None = None,
    ) -> Sequence[PurchaseAttemptAudit]: ...
