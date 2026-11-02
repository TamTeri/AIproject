"""PurchaseCoordinator: the one purchase path (standard checkout and quick buy).

Every attempt runs in exactly one PostgreSQL transaction owned here. Ports
(identity, events, quotes, inventory, payments, orders, audit, limits,
idempotency, request rate) receive that transaction and never commit or roll
back on their own.

Validation order ([TEMPORARY_MVP_DEFAULT] precedence, Call 5 additions marked *):
auth -> *one-time form key (a repeat replays here) -> *request limit -> event -> *sales closed ->
currency -> quantity -> hold ownership/expiry -> *discount still valid ->
limit -> pricing -> inventory (*sold out vs not enough left) -> payment.

Audit (audit-001/004/008, purchase-007): every submitted attempt writes one
append-only record (time, buyer, event, quantity, currency, outcome) in the
same transaction. If the transaction itself blows up, it is rolled back and an
``internal_error`` record is written in a fresh transaction, so the earliest,
buggiest attempts still leave a trace (Call 4).

Duplicate submissions (purchase-014, Call 5): each purchase form carries a
one-time key. The first request with a key is processed and its result stored
in the same transaction; any repeat gets that stored result back, creates
nothing, and is audited as ``replayed``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.audit.models import PurchaseAttemptAudit
from app.inventory.models import HoldReleaseReason, HoldStatus
from app.pricing.calculator import MAX_QUANTITY
from app.purchase.models import (
    CheckoutResult,
    IdempotencyDecision,
    PaymentRequest,
    PurchaseOutcome,
    PurchasePolicy,
    PurchaseRequest,
    PurchaseResult,
    QuoteSnapshot,
    RecordRef,
    audit_category,
)

# A whole number in ASCII digits, optionally signed, optionally written "2.0".
# (str.isdigit() also accepts "²" and "①", which int() cannot read: Part 5 ST-20.)
_WHOLE_NUMBER = re.compile(r"[+-]?[0-9]+(?:\.0+)?")
_MAX_QUANTITY_DIGITS = 9
# One-time form keys: what secrets.token_urlsafe() produces, bounded like the DB column.
_FORM_KEY = re.compile(r"[A-Za-z0-9_-]{16,128}")


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
    claimed_key: str | None = None  # set once this request owns its one-time key
    extra: dict[str, Any] = field(default_factory=dict)


class _Rejected(Exception):
    def __init__(self, outcome: PurchaseOutcome, hold: Any = None, available: int | None = None) -> None:
        super().__init__(str(outcome))
        self.outcome = outcome
        self.hold = hold
        self.available = available


class _Replay(Exception):
    """The one-time key was already used: hand back the first result."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__("replay")
        self.payload = payload


def classify_quantity(raw: object) -> tuple[int | None, PurchaseOutcome | None]:
    """Server-side quantity validation (purchase-001/002/017).

    Returns ``(quantity, None)`` for a valid quantity, otherwise ``(None, reason)``
    where the reason says *why*, so the buyer gets a specific message.
    """
    if isinstance(raw, bool) or raw is None:
        return None, PurchaseOutcome.INVALID_QUANTITY
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not _WHOLE_NUMBER.fullmatch(text):
            return None, PurchaseOutcome.INVALID_QUANTITY
        digits = text.lstrip("+-").split(".", 1)[0].lstrip("0")
        if len(digits) > _MAX_QUANTITY_DIGITS:  # never hand int() thousands of digits
            negative = text.startswith("-")
            return None, PurchaseOutcome.QUANTITY_NEGATIVE if negative else PurchaseOutcome.LIMIT_EXCEEDED
        value = int(text.split(".", 1)[0])
    else:
        return None, PurchaseOutcome.INVALID_QUANTITY
    if value == 0:
        return None, PurchaseOutcome.QUANTITY_ZERO
    if value < 0:
        return None, PurchaseOutcome.QUANTITY_NEGATIVE
    if value > MAX_QUANTITY:
        return None, PurchaseOutcome.LIMIT_EXCEEDED
    return value, None


def parse_quantity(raw: object) -> int | None:
    """The valid quantity, or None if it is invalid for any reason."""
    return classify_quantity(raw)[0]


def parse_currency(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    code = raw.strip().upper()
    if len(code) != 3 or not code.isascii() or not code.isalpha():
        return None
    return code


def _audit_quantity(raw: object) -> int | None:
    """The quantity as typed, for the audit row (bounded 0..999,999; else None)."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if 0 <= raw <= 999_999 else None
    if isinstance(raw, str):
        text = raw.strip()
        if _WHOLE_NUMBER.fullmatch(text) and not text.startswith("-"):
            digits = text.lstrip("+").split(".", 1)[0]
            if len(digits) <= 6:
                return int(digits)
    return None


def _audit_currency(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()[:16]
    if not value or not value.isascii() or any(c.isspace() for c in value):
        return None
    return value


def _form_key(raw: object) -> str | None:
    return raw if isinstance(raw, str) and _FORM_KEY.fullmatch(raw) else None


def _request_hash(operation: str, **fields: object) -> str:
    text = json.dumps({"operation": operation, **{k: str(v) for k, v in fields.items()}}, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        idempotency=None,
        request_rate=None,
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
        # Optional so a feature can be unit-tested without them; the wiring
        # always supplies both, which makes the one-time form key required.
        self._idempotency = idempotency
        self._request_rate = request_rate

    # ------------------------------------------------------------------ API

    def start_checkout(self, request: PurchaseRequest) -> CheckoutResult:
        """Validate, price and place a ten-minute hold (inventory-005)."""
        facts = self._facts(request)

        def work(tx: Any) -> CheckoutResult:
            buyer_id, now = self._begin(tx, facts)
            try:
                self._guard(
                    tx,
                    buyer_id,
                    now,
                    facts,
                    _request_hash(
                        "checkout_start",
                        event_id=request.event_id,
                        quantity=request.quantity,
                        currency=request.currency,
                    ),
                )
                hold, quote = self._reserve(tx, buyer_id, now, request, facts)
            except _Replay as replay:
                return self._replayed(tx, now, facts, replay.payload, CheckoutResult)
            except _Rejected as rejected:
                record = self._append_audit(tx, now, facts, rejected.outcome)
                result = CheckoutResult(
                    rejected.outcome, str(rejected.outcome), buyer_id, None, None, record, rejected.available
                )
                return self._remember(tx, facts, result)
            result = CheckoutResult(PurchaseOutcome.HOLD_CREATED, "hold_created", buyer_id, hold, quote, None)
            return self._remember(tx, facts, result)

        return self._run(work, facts)

    def pay(self, payment: PaymentRequest) -> PurchaseResult:
        """Complete a held checkout with the simulated payment step."""
        facts = _AttemptFacts(request_id=payment.request_id, idempotency_key=payment.idempotency_key)

        def work(tx: Any) -> PurchaseResult:
            buyer_id, now = self._begin(tx, facts)
            try:
                self._guard(
                    tx,
                    buyer_id,
                    now,
                    facts,
                    _request_hash("pay", hold_id=payment.hold_id, payment_choice=payment.payment_choice),
                )
                hold = self._owned_active_hold(tx, buyer_id, now, payment.hold_id, facts)
                self._still_on_sale(tx, buyer_id, now, hold)
                self._discount_still_applies(tx, buyer_id, now, hold)
            except _Replay as replay:
                return self._replayed(tx, now, facts, replay.payload, PurchaseResult)
            except _Rejected as rejected:
                record = self._append_audit(tx, now, facts, rejected.outcome)
                result = PurchaseResult(
                    rejected.outcome, str(rejected.outcome), buyer_id, rejected.hold, None, record
                )
                return self._remember(tx, facts, result)
            quote = hold.quote_snapshot
            result = self._complete(tx, buyer_id, now, hold, quote, payment.payment_choice, facts)
            return self._remember(tx, facts, result)

        return self._run(work, facts)

    def purchase(self, request: PurchaseRequest, *, payment_choice: str = "approve") -> PurchaseResult:
        """One-step purchase used by quick buy (purchase-011): same validation,
        same hold, same payment and audit path as the standard checkout."""
        facts = self._facts(request)

        def work(tx: Any) -> PurchaseResult:
            buyer_id, now = self._begin(tx, facts)
            try:
                self._guard(
                    tx,
                    buyer_id,
                    now,
                    facts,
                    _request_hash(
                        "quick_buy",
                        event_id=request.event_id,
                        quantity=request.quantity,
                        currency=request.currency,
                    ),
                )
                hold, quote = self._reserve(tx, buyer_id, now, request, facts)
            except _Replay as replay:
                return self._replayed(tx, now, facts, replay.payload, PurchaseResult)
            except _Rejected as rejected:
                record = self._append_audit(tx, now, facts, rejected.outcome)
                result = PurchaseResult(
                    rejected.outcome, str(rejected.outcome), buyer_id, None, None, record, rejected.available
                )
                return self._remember(tx, facts, result)
            result = self._complete(tx, buyer_id, now, hold, quote, payment_choice, facts)
            return self._remember(tx, facts, result)

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

    def reject_unauthenticated(self, request: PurchaseRequest) -> CheckoutResult:
        """purchase-016: a purchase from someone not logged in creates nothing,
        but is still recorded (Thuy: "all rejected ... all logged")."""
        facts = _AttemptFacts(
            request_id=request.request_id,
            quantity=_audit_quantity(request.quantity),
            currency=_audit_currency(request.currency),
        )

        def work(tx: Any) -> CheckoutResult:
            now = _aware(self._database_time.now(tx))
            event_id = str(request.event_id or "")
            if event_id and self._events.event_exists(tx, event_id):
                facts.event_id = event_id
            record = self._append_audit(tx, now, facts, PurchaseOutcome.NOT_AUTHENTICATED)
            return CheckoutResult(
                PurchaseOutcome.NOT_AUTHENTICATED, "not_authenticated", None, None, None, record
            )

        return self._run(work, facts)

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _facts(request: PurchaseRequest) -> _AttemptFacts:
        return _AttemptFacts(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            quantity=_audit_quantity(request.quantity),
            currency=_audit_currency(request.currency),
        )

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

    def _guard(self, tx: Any, buyer_id: str, now: datetime, facts: _AttemptFacts, request_hash: str) -> None:
        """Call 5 checks that run before anything is looked up or reserved.

        The one-time key is looked up *before* the request limit, so a repeat of
        a form that was already processed gets its first result back and is
        never refused as rate-limited, nor counted (Part 5 code review).
        """
        key = _form_key(facts.idempotency_key)
        facts.idempotency_key = key  # never write an unchecked key into the audit row
        if self._idempotency is None:
            self._count_request(tx, buyer_id, now)
            return
        if key is None:
            self._count_request(tx, buyer_id, now)
            raise _Rejected(PurchaseOutcome.IDEMPOTENCY_KEY_REQUIRED)

        claim = self._idempotency.claim(tx=tx, buyer_id=buyer_id, key=key, request_hash=request_hash)
        if claim.decision is IdempotencyDecision.REPLAY:
            raise _Replay(dict(claim.payload or {}))
        if claim.decision is IdempotencyDecision.CONFLICT:
            self._count_request(tx, buyer_id, now)
            raise _Rejected(PurchaseOutcome.IDEMPOTENCY_CONFLICT)
        try:
            self._count_request(tx, buyer_id, now)
        except _Rejected:
            # Over the limit: hand the key back so the same form works once the minute has passed.
            self._idempotency.release(tx=tx, buyer_id=buyer_id, key=key)
            raise
        facts.claimed_key = key

    def _count_request(self, tx: Any, buyer_id: str, now: datetime) -> None:
        """purchase-015: count this request; refuse it once the account is over the limit."""
        if self._request_rate is None:
            return
        count = self._request_rate.count_request(
            tx=tx, buyer_id=buyer_id, now=now, window_seconds=self._policy.rate_limit_window_seconds
        )
        if count > self._policy.rate_limit_requests:
            raise _Rejected(PurchaseOutcome.RATE_LIMITED)

    def _remember(self, tx: Any, facts: _AttemptFacts, result):
        """Store the first result for this form key, so repeats can replay it."""
        if self._idempotency is not None and facts.claimed_key is not None:
            hold = getattr(result, "hold", None)
            order = getattr(result, "order", None)
            self._idempotency.complete(
                tx=tx,
                buyer_id=facts.buyer_id,
                key=facts.claimed_key,
                payload={
                    "outcome": str(result.outcome),
                    "reason_code": result.reason_code,
                    "event_id": facts.event_id,
                    "hold_id": str(hold.id) if hold is not None else None,
                    "order_id": str(order.id) if order is not None else None,
                    "available": result.available,
                },
            )
        return result

    def _replayed(self, tx: Any, now: datetime, facts: _AttemptFacts, payload: dict[str, Any], result_type):
        """Answer a repeat submission with the first result; create nothing new."""
        hold_id = payload.get("hold_id")
        order_id = payload.get("order_id")
        facts.event_id = payload.get("event_id") or facts.event_id
        facts.hold_id = hold_id
        record = self._append_audit(tx, now, facts, PurchaseOutcome.REPLAYED, order_id=order_id)
        outcome = PurchaseOutcome(str(payload.get("outcome") or PurchaseOutcome.REPLAYED))
        hold = RecordRef(str(hold_id)) if hold_id else None
        second = RecordRef(str(order_id)) if result_type is PurchaseResult and order_id else None
        return result_type(
            outcome,
            str(payload.get("reason_code") or outcome),
            facts.buyer_id,
            hold,
            second,
            record,
            payload.get("available"),
            True,
        )

    def _reserve(
        self, tx: Any, buyer_id: str, now: datetime, request: PurchaseRequest, facts: _AttemptFacts
    ) -> tuple[Any, QuoteSnapshot]:
        event_id = str(request.event_id)
        if not self._events.lock_event(tx, event_id):
            raise _Rejected(PurchaseOutcome.EVENT_NOT_FOUND)
        facts.event_id = event_id
        if self._events.sales_closed(tx, event_id, now):
            raise _Rejected(PurchaseOutcome.SALES_CLOSED)

        currency = parse_currency(request.currency)
        if currency is None or currency not in self._quotes.supported_currencies(tx):
            raise _Rejected(PurchaseOutcome.UNSUPPORTED_CURRENCY)
        facts.currency = currency

        quantity, problem = classify_quantity(request.quantity)
        if quantity is None:
            raise _Rejected(problem or PurchaseOutcome.INVALID_QUANTITY)
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
            # purchase-017: "sold out" and "only N left" are different messages.
            left = max(int(self._inventory.available(tx, event_id=event_id, now=now)), 0)
            if left == 0:
                raise _Rejected(PurchaseOutcome.SOLD_OUT, available=0)
            raise _Rejected(PurchaseOutcome.NOT_ENOUGH_TICKETS, available=left)
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

    def _still_on_sale(self, tx: Any, buyer_id: str, now: datetime, hold: Any) -> None:
        """purchase-018: a hold placed just before the start cannot be paid after it."""
        if self._events.sales_closed(tx, str(hold.event_id), now):
            released = self._inventory.release_hold(
                tx=tx, hold_id=hold.id, buyer_id=buyer_id, reason=HoldReleaseReason.CANCELLED, now=now
            )
            raise _Rejected(PurchaseOutcome.SALES_CLOSED, released)

    def _discount_still_applies(self, tx: Any, buyer_id: str, now: datetime, hold: Any) -> None:
        """pricing-011 (Kenji's finding 1): the frozen price may include a student
        discount; if the account's email no longer qualifies, do not honour it."""
        quote = hold.quote_snapshot
        if quote is None or quote.discount_minor <= 0:
            return
        if self._quotes.discount_still_applies(tx=tx, buyer_id=buyer_id, quote=quote):
            return
        released = self._inventory.release_hold(
            tx=tx, hold_id=hold.id, buyer_id=buyer_id, reason=HoldReleaseReason.CANCELLED, now=now
        )
        raise _Rejected(PurchaseOutcome.ELIGIBILITY_CHANGED, released)

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
            idempotency_key=_form_key(facts.idempotency_key),
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


__all__ = ["PurchaseCoordinator", "classify_quantity", "parse_currency", "parse_quantity"]
