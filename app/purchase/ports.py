from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.inventory.models import Hold
    from app.purchase.models import IdempotencyClaim, PaymentResult, PurchaseResult, QuoteSnapshot


@runtime_checkable
class PostgresTransactionContext(Protocol):
    """One caller-owned PostgreSQL transaction; repositories never commit it."""

    def execute(self, statement: str, parameters: Mapping[str, object] | None = None) -> Any: ...

    def fetch_one(
        self, statement: str, parameters: Mapping[str, object] | None = None
    ) -> Mapping[str, Any] | None: ...

    def fetch_all(
        self, statement: str, parameters: Mapping[str, object] | None = None
    ) -> Sequence[Mapping[str, Any]]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class TransactionProvider(Protocol):
    def begin(self) -> PostgresTransactionContext: ...


class BuyerIdentityPort(Protocol):
    """Resolves the authenticated subject; no request field is authoritative."""

    def current_buyer_id(self, tx: PostgresTransactionContext) -> str: ...


class QuotePort(Protocol):
    """Resolves an immutable server-owned quote; callers cannot submit a price."""

    def quote(
        self,
        *,
        tx: PostgresTransactionContext,
        buyer_id: str,
        event_id: str,
        quantity: int,
        currency: str,
    ) -> QuoteSnapshot: ...


class QuoteCurrenciesPort(Protocol):
    def supported_currencies(self, tx: PostgresTransactionContext) -> set[str]: ...


class PurchasableEventPort(Protocol):
    """Locks the event row (SELECT ... FOR UPDATE) so limit and capacity checks
    for one event run one at a time. False if the event is missing/inactive."""

    def lock_event(self, tx: PostgresTransactionContext, event_id: str) -> bool: ...


class PurchaseLimitPort(Protocol):
    """Tickets the buyer already owns or holds (unexpired) for the event."""

    def committed_quantity(self, tx: PostgresTransactionContext, *, buyer_id: str, event_id: str) -> int: ...


class PaymentPort(Protocol):
    """Simulated payment (purchase-004): no external provider in version one."""

    def simulate(
        self,
        *,
        tx: PostgresTransactionContext,
        buyer_id: str,
        hold: Hold,
        quote_snapshot: QuoteSnapshot,
        payment_choice: str = "approve",
    ) -> PaymentResult: ...


class IdempotencyPort(Protocol):
    """Optional local/demo seam; durable PostgreSQL storage is a later schema task."""

    def claim(
        self,
        *,
        tx: PostgresTransactionContext,
        buyer_id: str,
        operation: str,
        key: str,
        request_hash: str,
    ) -> IdempotencyClaim: ...

    def complete(
        self,
        *,
        tx: PostgresTransactionContext,
        buyer_id: str,
        operation: str,
        key: str,
        request_hash: str,
        result: PurchaseResult,
    ) -> None: ...
