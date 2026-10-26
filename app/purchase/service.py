"""[TEMPORARY_MVP_DEFAULT] Smallest purchase orchestration for the buyer tracer.

PurchaseCoordinator owns exactly one PostgreSQL transaction context per
purchase attempt. Downstream ports (identity, quotes, inventory, payments,
orders, audit) receive that same transaction and never commit or roll back
independently. Hold duration (10 minutes), release/cancel mechanics beyond
payment-failure release, and idempotency are explicitly out of scope for this
tracer slice; see app/purchase/ports.py for the full port contracts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.purchase.models import (
    PurchaseOutcome,
    PurchaseRequest,
    PurchaseResult,
)

_TEMPORARY_HOLD_MINUTES = 10


class PurchaseCoordinator:
    """Orchestrates one buyer purchase attempt inside a single transaction."""

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
    ) -> None:
        self._transactions = transactions
        self._identity = identity
        self._database_time = database_time
        self._quotes = quotes
        self._inventory = inventory
        self._payments = payments
        self._orders = orders
        self._audit = audit

    def purchase(self, request: PurchaseRequest) -> PurchaseResult:
        tx = self._transactions.begin()
        try:
            buyer_id = self._identity.current_buyer_id(tx)
            now = self._database_time.now(tx)

            quote = self._quotes.quote(
                tx=tx,
                buyer_id=buyer_id,
                event_id=request.event_id,
                quantity=request.quantity,
                currency=request.currency,
            )

            expires_at = now + timedelta(minutes=_TEMPORARY_HOLD_MINUTES)
            hold = self._inventory.allocate_hold(
                tx=tx,
                buyer_id=buyer_id,
                event_id=request.event_id,
                quantity=request.quantity,
                expires_at=expires_at,
                quote_snapshot=quote,
            )

            payment_result = self._payments.simulate(
                tx=tx,
                buyer_id=buyer_id,
                hold=hold,
                quote_snapshot=quote,
            )

            if payment_result.succeeded:
                converted_hold = self._inventory.convert_hold(
                    tx=tx, hold_id=hold.id, buyer_id=buyer_id, now=now
                )
                order = self._orders.create_order_snapshot(
                    tx=tx, buyer_id=buyer_id, hold=converted_hold, quote_snapshot=quote
                )
                outcome = PurchaseOutcome.SUCCESS
                reason_code = "OK"
                audit_record = self._build_audit_record(
                    now=now,
                    buyer_id=buyer_id,
                    request=request,
                    outcome=outcome,
                    reason_code=reason_code,
                    hold_id=hold.id,
                    order_id=order.id,
                )
                self._audit.append(tx=tx, record=audit_record)
                tx.commit()
                return PurchaseResult(
                    outcome=outcome,
                    reason_code=reason_code,
                    buyer_id=buyer_id,
                    hold=converted_hold,
                    order=order,
                    audit=audit_record,
                )

            released_hold = self._inventory.release_hold(
                tx=tx,
                hold_id=hold.id,
                buyer_id=buyer_id,
                reason="payment_failed",
                now=now,
            )
            outcome = PurchaseOutcome.PAYMENT_FAILED
            reason_code = payment_result.reason_code
            audit_record = self._build_audit_record(
                now=now,
                buyer_id=buyer_id,
                request=request,
                outcome=outcome,
                reason_code=reason_code,
                hold_id=hold.id,
                order_id=None,
            )
            self._audit.append(tx=tx, record=audit_record)
            tx.commit()
            return PurchaseResult(
                outcome=outcome,
                reason_code=reason_code,
                buyer_id=buyer_id,
                hold=released_hold,
                order=None,
                audit=audit_record,
            )
        except Exception:
            tx.rollback()
            raise

    def _build_audit_record(
        self,
        *,
        now: datetime,
        buyer_id: str,
        request: PurchaseRequest,
        outcome: PurchaseOutcome,
        reason_code: str,
        hold_id: str | None,
        order_id: str | None,
    ):
        from app.audit.models import PurchaseAttemptAudit

        submitted_at = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        return PurchaseAttemptAudit(
            attempt_id=str(uuid4()),
            submitted_at=submitted_at,
            buyer_id=buyer_id,
            event_id=request.event_id,
            quantity=request.quantity,
            currency=request.currency,
            outcome=str(outcome),
            reason_code=reason_code,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            hold_id=hold_id,
            order_id=order_id,
        )


__all__ = ["PurchaseCoordinator"]
