from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.inventory.models import Hold
    from app.purchase.models import IdempotencyClaim, PaymentResult, QuoteSnapshot


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


class DiscountRecheckPort(Protocol):
    """pricing-011: is the buyer still eligible for the discount frozen in this quote?"""

    def discount_still_applies(
        self, *, tx: PostgresTransactionContext, buyer_id: str, quote: QuoteSnapshot
    ) -> bool: ...


class PurchasableEventPort(Protocol):
    """Locks the event row (SELECT ... FOR UPDATE) so limit and capacity checks
    for one event run one at a time. False if the event is missing/inactive."""

    def lock_event(self, tx: PostgresTransactionContext, event_id: str) -> bool: ...

    def event_exists(self, tx: PostgresTransactionContext, event_id: str) -> bool:
        """Same check without a lock (used for not-logged-in attempts)."""
        ...

    def sales_closed(self, tx: PostgresTransactionContext, event_id: str, now: datetime) -> bool:
        """purchase-018: True once the event has started."""
        ...


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
    """purchase-014: one-time form keys, stored in ``idempotency_records``.

    ``claim`` inserts the key inside the purchase transaction. A second request
    with the same key waits for the first transaction, then sees its stored
    result (REPLAY) or a different request hash (CONFLICT).
    """

    def claim(
        self, *, tx: PostgresTransactionContext, buyer_id: str, key: str, request_hash: str
    ) -> IdempotencyClaim: ...

    def complete(
        self, *, tx: PostgresTransactionContext, buyer_id: str, key: str, payload: Mapping[str, object]
    ) -> None: ...

    def release(self, *, tx: PostgresTransactionContext, buyer_id: str, key: str) -> None:
        """Forget a key this request claimed but did not use (it was over the request limit)."""
        ...


class RequestRatePort(Protocol):
    """purchase-015: count this request in the buyer's current window; return the count."""

    def count_request(
        self, *, tx: PostgresTransactionContext, buyer_id: str, now: datetime, window_seconds: int
    ) -> int: ...
