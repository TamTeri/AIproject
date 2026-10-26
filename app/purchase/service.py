"""PurchaseCoordinator: the one purchase path (standard checkout and quick buy).

Every attempt runs in exactly one PostgreSQL transaction owned here. Ports
(identity, events, quotes, inventory, payments, orders, audit, limits) receive
that transaction and never commit or roll back on their own.

Validation order ([TEMPORARY_MVP_DEFAULT] precedence from seed/config):
auth -> event -> currency -> quantity -> hold ownership/expiry -> limit ->
pricing -> inventory -> payment.

Audit (audit-001/004, purchase-007): every submitted attempt writes one
append-only record (time, buyer, event, quantity, currency, outcome) in the
same transaction. If the transaction itself blows up, it is rolled back and an
``internal_error`` record is written in a fresh transaction, so the earliest,
buggiest attempts still leave a trace (Call 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.audit.models import PurchaseAttemptAudit
from app.inventory.models import HoldReleaseReason, HoldStatus
from app.pricing.calculator import MAX_QUANTITY
from app.purchase.models import (
    CheckoutResult,
    PaymentRequest,
    PurchaseOutcome,
    PurchasePolicy,
    PurchaseRequest,
    PurchaseResult,
    QuoteSnapshot,
    audit_category,
)


@dataclass
class _AttemptFacts:
    """What we know about an attempt so far; used for its audit record."""

    buyer_id: str | None = None
    event_id: str | None = None
    quantity: int | None = None
    currency: str | None = None
    hold_id: str | None = None
    request_id: str | None = None
    idempotency_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class _Rejected(Exception):
    def __init__(self, outcome: PurchaseOutcome, hold: Any = None) -> None:
        super().__init__(str(outcome))
        self.outcome = outcome
        self.hold = hold


def parse_quantity(raw: object) -> int | None:
    """Server-side quantity validation (purchase-001/002). None means invalid."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str) and raw.strip().isdigit() and len(raw.strip()) <= 7:
        value = int(raw.strip())
    else:
        return None
    if not 1 <= value <= MAX_QUANTITY:
        return None
    return value


def parse_currency(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    code = raw.strip().upper()
    if len(code) != 3 or not code.isascii() or not code.isalpha():
        return None
    return code


def _audit_quantity(raw: object) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int) and 0 <= raw <= 1_000_000:
        return raw
    if isinstance(raw, str) and raw.strip().isdigit() and len(raw.strip()) <= 7:
        return int(raw.strip())
    return None


def _audit_currency(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()[:16]
    if not value or not value.isascii() or any(c.isspace() for c in value):
        return None
    return value


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class PurchaseCoordinator:
    def __init__(
        self,
        *,
        transactions,
        identity,
        database_time,
        quotes,
        inventory,
        payments,
        orders,
        audit,
        events,
        limits,
        policy: PurchasePolicy | None = None,
    ) -> None:
        self._transactions = transactions
        self._identity = identity
        self._database_time = database_time
        self._quotes = quotes
        self._inventory = inventory
        self._payments = payments
        self._orders = orders
        self._audit = audit
        self._events = events
        self._limits = limits
        self._policy = policy or PurchasePolicy()

    # ------------------------------------------------------------------ API

    def start_checkout(self, request: PurchaseRequest) -> CheckoutResult:
        """Validate, price and place a ten-minute hold (inventory-005)."""
        facts = _AttemptFacts(request_id=request.request_id, idempotency_key=request.idempotency_key)

        def work(tx: Any) -> CheckoutResult:
            buyer_id, now = self._begin(tx, facts)
            try:
                hold, quote = self._reserve(tx, buyer_id, now, request, facts)
            except _Rejected as rejected:
                record = self._append_audit(tx, now, facts, rejected.outcome)
                return CheckoutResult(rejected.outcome, str(rejected.outcome), buyer_id, None, None, record)
            return CheckoutResult(PurchaseOutcome.HOLD_CREATED, "hold_created", buyer_id, hold, quote, None)

        return self._run(work, facts)

    def pay(self, payment: PaymentRequest) -> PurchaseResult:
        """Complete a held checkout with the simulated payment step."""
        facts = _AttemptFacts(request_id=payment.request_id, idempotency_key=payment.idempotency_key)

        def work(tx: Any) -> PurchaseResult:
            buyer_id, now = self._begin(tx, facts)
            try:
                hold = self._owned_active_hold(tx, buyer_id, now, payment.hold_id, facts)
            except _Rejected as rejected:
                record = self._append_audit(tx, now, facts, rejected.outcome)
                return PurchaseResult(
                    rejected.outcome, str(rejected.outcome), buyer_id, rejected.hold, None, record
                )
            quote = hold.quote_snapshot
            return self._complete(tx, buyer_id, now, hold, quote, payment.payment_choice, facts)

        return self._run(work, facts)

    def purchase(self, request: PurchaseRequest, *, payment_choice: str = "approve") -> PurchaseResult:
        """One-step purchase used by quick buy (purchase-011): same validation,
        same hold, same payment and audit path as the standard checkout."""
        facts = _AttemptFacts(request_id=request.request_id, idempotency_key=request.idempotency_key)

        def work(tx: Any) -> PurchaseResult:
            buyer_id, now = self._begin(tx, facts)
            try:
                hold, quote = self._reserve(tx, buyer_id, now, request, facts)
            except _Rejected as rejected:
                record = self._append_audit(tx, now, facts, rejected.outcome)
                return PurchaseResult(rejected.outcome, str(rejected.outcome), buyer_id, None, None, record)
            return self._complete(tx, buyer_id, now, hold, quote, payment_choice, facts)

        return self._run(work, facts)

    def cancel(self, hold_id: str) -> CheckoutResult:
        """Buyer abandons checkout: give the tickets back immediately."""
        facts = _AttemptFacts()

        def work(tx: Any) -> CheckoutResult:
            buyer_id, now = self._begin(tx, facts)
            try:
                hold = self._owned_active_hold(tx, buyer_id, now, hold_id, facts)
            except _Rejected as rejected:
                return CheckoutResult(
                    rejected.outcome, str(rejected.outcome), buyer_id, rejected.hold, None, None
                )
            released = self._inventory.release_hold(
                tx=tx, hold_id=hold.id, buyer_id=buyer_id, reason=HoldReleaseReason.CANCELLED, now=now
            )
            record = self._append_audit(tx, now, facts, PurchaseOutcome.CANCELLED)
            return CheckoutResult(
                PurchaseOutcome.CANCELLED, "cancelled", buyer_id, released, hold.quote_snapshot, record
            )

        return self._run(work, facts)

    # -------------------------------------------------------------- helpers

    def _run(self, work, facts: _AttemptFacts):
        tx = self._transactions.begin()
        try:
            result = work(tx)
        except Exception:
            tx.rollback()
            self._record_internal_error(facts)
            raise
        tx.commit()
        return result

    def _begin(self, tx: Any, facts: _AttemptFacts) -> tuple[str, datetime]:
        buyer_id = self._identity.current_buyer_id(tx)
        facts.buyer_id = buyer_id
        now = _aware(self._database_time.now(tx))
        return buyer_id, now

    def _reserve(
        self, tx: Any, buyer_id: str, now: datetime, request: PurchaseRequest, facts: _AttemptFacts
    ) -> tuple[Any, QuoteSnapshot]:
        facts.quantity = _audit_quantity(request.quantity)
        facts.currency = _audit_currency(request.currency)

        event_id = str(request.event_id)
        if not self._events.lock_event(tx, event_id):
            raise _Rejected(PurchaseOutcome.EVENT_NOT_FOUND)
        facts.event_id = event_id

        currency = parse_currency(request.currency)
        if currency is None or currency not in self._quotes.supported_currencies(tx):
            raise _Rejected(PurchaseOutcome.UNSUPPORTED_CURRENCY)
        facts.currency = currency

        quantity = parse_quantity(request.quantity)
        if quantity is None:
            raise _Rejected(PurchaseOutcome.INVALID_QUANTITY)
        facts.quantity = quantity

        already = self._limits.committed_quantity(tx, buyer_id=buyer_id, event_id=event_id)
        if already + quantity > self._policy.per_account_event_limit:
            raise _Rejected(PurchaseOutcome.LIMIT_EXCEEDED)

        quote = self._quotes.quote(
            tx=tx, buyer_id=buyer_id, event_id=event_id, quantity=quantity, currency=currency
        )
        hold = self._inventory.allocate_hold(
            tx=tx,
            buyer_id=buyer_id,
            event_id=event_id,
            quantity=quantity,
            expires_at=now + timedelta(minutes=self._policy.hold_minutes),
            quote_snapshot=quote,
        )
        if hold is None:
            raise _Rejected(PurchaseOutcome.SOLD_OUT)
        facts.hold_id = str(hold.id)
        return hold, quote

    def _owned_active_hold(
        self, tx: Any, buyer_id: str, now: datetime, hold_id: str, facts: _AttemptFacts
    ) -> Any:
        hold = self._inventory.get_hold_for_buyer(tx=tx, hold_id=str(hold_id), buyer_id=buyer_id)
        if hold is None:
            raise _Rejected(PurchaseOutcome.HOLD_NOT_FOUND)
        facts.hold_id = str(hold.id)
        facts.event_id = str(hold.event_id)
        facts.quantity = hold.quantity
        quote = hold.quote_snapshot
        facts.currency = getattr(quote, "currency", None)
        if HoldStatus(str(hold.status)) is not HoldStatus.ACTIVE:
            raise _Rejected(PurchaseOutcome.HOLD_TERMINAL, hold)
        if _aware(hold.expires_at) <= now:
            released = self._inventory.release_hold(
                tx=tx, hold_id=hold.id, buyer_id=buyer_id, reason=HoldReleaseReason.EXPIRED, now=now
            )
            raise _Rejected(PurchaseOutcome.HOLD_EXPIRED, released)
        return hold

    def _complete(
        self,
        tx: Any,
        buyer_id: str,
        now: datetime,
        hold: Any,
        quote: QuoteSnapshot,
        payment_choice: str,
        facts: _AttemptFacts,
    ) -> PurchaseResult:
        payment = self._payments.simulate(
            tx=tx, buyer_id=buyer_id, hold=hold, quote_snapshot=quote, payment_choice=payment_choice
        )
        if not payment.succeeded:
            released = self._inventory.release_hold(
                tx=tx, hold_id=hold.id, buyer_id=buyer_id, reason=HoldReleaseReason.PAYMENT_FAILED, now=now
            )
            record = self._append_audit(tx, now, facts, PurchaseOutcome.PAYMENT_FAILED)
            return PurchaseResult(
                PurchaseOutcome.PAYMENT_FAILED, payment.reason_code, buyer_id, released, None, record
            )

        converted = self._inventory.convert_hold(tx=tx, hold_id=hold.id, buyer_id=buyer_id, now=now)
        if converted is None:  # lost a race with expiry/cancel inside the lock window
            record = self._append_audit(tx, now, facts, PurchaseOutcome.HOLD_TERMINAL)
            return PurchaseResult(
                PurchaseOutcome.HOLD_TERMINAL, "hold_terminal", buyer_id, hold, None, record
            )
        order = self._orders.create_order_snapshot(
            tx=tx, buyer_id=buyer_id, hold=converted, quote_snapshot=quote
        )
        record = self._append_audit(tx, now, facts, PurchaseOutcome.SUCCESS, order_id=str(order.id))
        return PurchaseResult(PurchaseOutcome.SUCCESS, "OK", buyer_id, converted, order, record)

    def _append_audit(
        self,
        tx: Any,
        now: datetime,
        facts: _AttemptFacts,
        outcome: PurchaseOutcome,
        *,
        order_id: str | None = None,
    ) -> PurchaseAttemptAudit:
        record = PurchaseAttemptAudit(
            attempt_id=str(uuid4()),
            submitted_at=now,
            buyer_id=facts.buyer_id,
            event_id=facts.event_id,
            quantity=facts.quantity,
            currency=facts.currency,
            outcome=str(audit_category(outcome)),
            reason_code=str(outcome),
            request_id=facts.request_id,
            idempotency_key=facts.idempotency_key,
            hold_id=facts.hold_id,
            order_id=order_id,
        )
        self._audit.append(tx=tx, record=record)
        return record

    def _record_internal_error(self, facts: _AttemptFacts) -> None:
        """Best effort: never hide the original exception."""
        try:
            tx = self._transactions.begin()
        except Exception:
            return
        try:
            self._append_audit(
                tx,
                datetime.now(UTC),
                # hold/order rows were rolled back, so do not reference them.
                _AttemptFacts(
                    buyer_id=facts.buyer_id,
                    event_id=facts.event_id,
                    quantity=facts.quantity,
                    currency=facts.currency,
                    request_id=facts.request_id,
                ),
                PurchaseOutcome.INTERNAL_ERROR,
            )
            tx.commit()
        except Exception:
            tx.rollback()


__all__ = ["PurchaseCoordinator", "parse_currency", "parse_quantity"]
