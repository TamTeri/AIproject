"""Call 5 purchase rules, unit-tested with in-memory fakes (no database).

purchase-014 duplicate submissions, purchase-015 request rate, purchase-016
not logged in, purchase-017 specific reasons, purchase-018 sales closed,
pricing-011 discount re-checked at payment, audit-008 reason codes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

import pytest

from app.inventory.models import HoldStatus
from app.purchase.models import (
    IdempotencyClaim,
    IdempotencyDecision,
    PaymentRequest,
    PurchaseOutcome,
    PurchasePolicy,
    PurchaseRequest,
    QuoteSnapshot,
)
from app.purchase.service import PurchaseCoordinator, classify_quantity
from tests.unit.purchase.fakes import (
    Audit,
    Buyer,
    Clock,
    Events,
    Inventory,
    Limits,
    Orders,
    Payments,
    Quotes,
    Transactions,
    World,
)

KEY = "k" * 32


@dataclass
class FakeIdempotency:
    """Behaves like PostgresIdempotency: one record per (buyer, key)."""

    records: dict[tuple[str, str], dict] = field(default_factory=dict)

    def claim(self, *, tx, buyer_id, key, request_hash):
        record = self.records.get((buyer_id, key))
        if record is None:
            self.records[(buyer_id, key)] = {"hash": request_hash, "payload": None}
            return IdempotencyClaim(IdempotencyDecision.NEW)
        if record["hash"] != request_hash or record["payload"] is None:
            return IdempotencyClaim(IdempotencyDecision.CONFLICT)
        return IdempotencyClaim(IdempotencyDecision.REPLAY, dict(record["payload"]))

    def complete(self, *, tx, buyer_id, key, payload):
        self.records[(buyer_id, key)]["payload"] = dict(payload)

    def release(self, *, tx, buyer_id, key):
        record = self.records.get((buyer_id, key))
        if record is not None and record["payload"] is None:
            del self.records[(buyer_id, key)]


@dataclass
class FakeRate:
    """Fixed window, like PostgresRequestRate."""

    clock: Clock
    windows: dict[str, tuple] = field(default_factory=dict)

    def count_request(self, *, tx, buyer_id, now, window_seconds):
        started, count = self.windows.get(buyer_id, (now, 0))
        if now - started >= timedelta(seconds=window_seconds):
            started, count = now, 0
        self.windows[buyer_id] = (started, count + 1)
        return count + 1


class DiscountQuotes(Quotes):
    """Quotes with a 10% discount, so the pay-time re-check has something to check."""

    def quote(self, *, tx, buyer_id, event_id, quantity, currency):
        subtotal = self.unit * quantity
        return QuoteSnapshot(
            event_id=event_id,
            quantity=quantity,
            currency=currency,
            exchange_rate=Decimal("1"),
            total_minor=subtotal - subtotal // 10,
            unit_price_minor=self.unit,
            subtotal_minor=subtotal,
            discount_minor=subtotal // 10,
            discount_percent=Decimal("10"),
            discount_reason="eligible",
        )


def coordinator(
    world: World, clock: Clock, *, buyer_id="7", quotes=None, idempotency=None, rate=None, **policy
):
    return PurchaseCoordinator(
        transactions=Transactions(),
        identity=Buyer(buyer_id),
        database_time=clock,
        quotes=quotes or Quotes(world),
        inventory=Inventory(world, clock),
        payments=Payments(),
        orders=Orders(world),
        audit=Audit(world),
        events=Events(world),
        limits=Limits(world, clock),
        policy=PurchasePolicy(hold_minutes=10, per_account_event_limit=4, **policy),
        idempotency=idempotency,
        request_rate=rate,
    )


def buy(quantity=1, currency="USD", key=KEY, event_id="1") -> PurchaseRequest:
    return PurchaseRequest(event_id=event_id, quantity=quantity, currency=currency, idempotency_key=key)


# ------------------------------------------------------- purchase-017 quantities


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", (None, PurchaseOutcome.QUANTITY_ZERO)),
        ("-0", (None, PurchaseOutcome.QUANTITY_ZERO)),
        ("-2", (None, PurchaseOutcome.QUANTITY_NEGATIVE)),
        ("2.0", (2, None)),
        ("+3", (3, None)),
        (" 4 ", (4, None)),
        ("1.5", (None, PurchaseOutcome.INVALID_QUANTITY)),
        ("1e3", (None, PurchaseOutcome.INVALID_QUANTITY)),
        ("0x10", (None, PurchaseOutcome.INVALID_QUANTITY)),
        ("²", (None, PurchaseOutcome.INVALID_QUANTITY)),  # "²": isdigit() True, int() fails
        ("٣", (None, PurchaseOutcome.INVALID_QUANTITY)),  # Arabic-Indic three
        ("9" * 5000, (None, PurchaseOutcome.LIMIT_EXCEEDED)),  # longer than int() will parse
        ("1001", (None, PurchaseOutcome.LIMIT_EXCEEDED)),
        ("-" + "9" * 20, (None, PurchaseOutcome.QUANTITY_NEGATIVE)),
    ],
)
def test_classify_quantity_gives_a_specific_reason(raw, expected):
    assert classify_quantity(raw) == expected


# ------------------------------------------------- purchase-014 duplicate submissions


def test_second_quick_buy_with_the_same_key_replays_the_first_order():
    world, clock = World(), Clock()
    keys = FakeIdempotency()
    hub = coordinator(world, clock, idempotency=keys)

    first = hub.purchase(buy())
    second = hub.purchase(buy())

    assert first.outcome is second.outcome is PurchaseOutcome.SUCCESS
    assert second.replayed and not first.replayed
    assert second.order.id == first.order.id
    assert len(world.orders) == 1
    assert [r.reason_code for r in world.audit] == ["success", "replayed"]
    assert world.audit[1].outcome == "replayed" and world.audit[1].order_id == first.order.id


def test_second_pay_with_the_same_key_replays_without_paying_again():
    world, clock = World(), Clock()
    hub = coordinator(world, clock, idempotency=FakeIdempotency())
    hold = hub.start_checkout(buy(quantity=2, key="a" * 32)).hold

    first = hub.pay(PaymentRequest(hold_id=hold.id, idempotency_key=KEY))
    second = hub.pay(PaymentRequest(hold_id=hold.id, idempotency_key=KEY))

    assert second.outcome is PurchaseOutcome.SUCCESS and second.replayed
    assert second.order.id == first.order.id
    assert len(world.orders) == 1


def test_a_replayed_rejection_stays_a_rejection():
    world, clock = World(capacity={"1": 1}), Clock()
    hub = coordinator(world, clock, idempotency=FakeIdempotency())
    first = hub.start_checkout(buy(quantity=3))
    second = hub.start_checkout(buy(quantity=3))
    assert first.outcome is second.outcome is PurchaseOutcome.NOT_ENOUGH_TICKETS
    assert second.replayed and second.available == 1


def test_missing_or_malformed_key_is_rejected_when_keys_are_required():
    world, clock = World(), Clock()
    hub = coordinator(world, clock, idempotency=FakeIdempotency())
    for key in (None, "", "short", "bad key with spaces!" * 3):
        result = hub.purchase(buy(key=key))
        assert result.outcome is PurchaseOutcome.IDEMPOTENCY_KEY_REQUIRED
    assert world.orders == []
    assert all(r.idempotency_key is None for r in world.audit)  # never store an unchecked key


def test_same_key_for_a_different_request_is_a_conflict():
    world, clock = World(), Clock()
    hub = coordinator(world, clock, idempotency=FakeIdempotency())
    hub.start_checkout(buy(quantity=1))
    changed = hub.start_checkout(buy(quantity=2))
    assert changed.outcome is PurchaseOutcome.IDEMPOTENCY_CONFLICT
    assert len(world.holds) == 1


def test_a_fresh_key_is_a_new_purchase():
    world, clock = World(), Clock()
    hub = coordinator(world, clock, idempotency=FakeIdempotency())
    hub.purchase(buy(key="a" * 32))
    hub.purchase(buy(key="b" * 32))
    assert len(world.orders) == 2


# ------------------------------------------------------- purchase-015 request rate


def test_eleventh_request_in_a_minute_is_rate_limited_and_audited():
    world, clock = World(), Clock()
    hub = coordinator(world, clock, rate=FakeRate(clock))
    outcomes = [hub.start_checkout(buy(quantity=0)).outcome for _ in range(10)]
    assert set(outcomes) == {PurchaseOutcome.QUANTITY_ZERO}

    limited = hub.start_checkout(buy(quantity=1))
    assert limited.outcome is PurchaseOutcome.RATE_LIMITED
    assert world.holds == {}
    assert world.audit[-1].reason_code == "rate_limited"

    clock.value += timedelta(seconds=61)  # a new window
    assert hub.start_checkout(buy(quantity=1)).outcome is PurchaseOutcome.HOLD_CREATED


def test_rate_limit_is_per_account():
    world, clock = World(), Clock()
    rate = FakeRate(clock)
    noisy = coordinator(world, clock, buyer_id="1", rate=rate)
    calm = coordinator(world, clock, buyer_id="2", rate=rate)
    for _ in range(11):
        noisy.start_checkout(buy(quantity=0))
    assert calm.purchase(buy()).outcome is PurchaseOutcome.SUCCESS


def test_rate_limit_numbers_come_from_the_policy():
    world, clock = World(), Clock()
    hub = coordinator(world, clock, rate=FakeRate(clock), rate_limit_requests=2)
    hub.start_checkout(buy(quantity=0))
    hub.start_checkout(buy(quantity=0))
    assert hub.start_checkout(buy(quantity=0)).outcome is PurchaseOutcome.RATE_LIMITED


# ------------------------------------------------------- purchase-016 not logged in


def test_not_logged_in_attempt_is_audited_and_creates_nothing():
    world, clock = World(), Clock()
    hub = coordinator(world, clock)
    result = hub.reject_unauthenticated(PurchaseRequest(event_id="1", quantity="2", currency="EUR"))
    assert result.outcome is PurchaseOutcome.NOT_AUTHENTICATED
    assert world.holds == {} and world.orders == []
    (record,) = world.audit
    assert (record.buyer_id, record.event_id, record.quantity, record.currency) == (None, "1", 2, "EUR")
    assert record.reason_code == "not_authenticated"


def test_not_logged_in_attempt_for_an_unknown_event_does_not_reference_it():
    world, clock = World(), Clock()
    hub = coordinator(world, clock)
    hub.reject_unauthenticated(PurchaseRequest(event_id="999", quantity="1", currency="USD"))
    assert world.audit[0].event_id is None


# --------------------------------------------------------- purchase-018 sales closed


def test_no_sales_once_the_event_has_started():
    world, clock = World(started={"1"}), Clock()
    hub = coordinator(world, clock)
    assert hub.purchase(buy()).outcome is PurchaseOutcome.SALES_CLOSED
    assert world.audit[0].reason_code == "sales_closed"


def test_a_hold_cannot_be_paid_after_the_event_starts():
    world, clock = World(), Clock()
    hub = coordinator(world, clock)
    hold = hub.start_checkout(buy(quantity=2)).hold
    world.started.add("1")
    result = hub.pay(PaymentRequest(hold_id=hold.id))
    assert result.outcome is PurchaseOutcome.SALES_CLOSED
    assert world.holds[hold.id].status is HoldStatus.CANCELLED
    assert world.orders == []


# ------------------------------------------------ pricing-011 discount re-checked


def test_discounted_hold_is_released_if_the_email_no_longer_qualifies():
    world, clock = World(), Clock()
    hub = coordinator(world, clock, quotes=DiscountQuotes(world))
    hold = hub.start_checkout(buy(quantity=2)).hold
    assert hold.quote_snapshot.discount_minor > 0

    world.eligible = False  # the buyer changed their email to a non-USF address
    result = hub.pay(PaymentRequest(hold_id=hold.id))

    assert result.outcome is PurchaseOutcome.ELIGIBILITY_CHANGED
    assert world.holds[hold.id].status is HoldStatus.CANCELLED
    assert world.orders == []
    assert world.audit[-1].reason_code == "eligibility_changed"


def test_discounted_hold_is_paid_normally_while_still_eligible():
    world, clock = World(), Clock()
    hub = coordinator(world, clock, quotes=DiscountQuotes(world))
    hold = hub.start_checkout(buy(quantity=2)).hold
    assert hub.pay(PaymentRequest(hold_id=hold.id)).outcome is PurchaseOutcome.SUCCESS


def test_holds_without_a_discount_are_not_rechecked():
    world, clock = World(eligible=False), Clock()
    hub = coordinator(world, clock)
    hold = hub.start_checkout(buy()).hold
    assert hub.pay(PaymentRequest(hold_id=hold.id)).outcome is PurchaseOutcome.SUCCESS


# ------------------------------------------- code-review fixes (Part 5)


def test_a_repeat_is_replayed_even_when_the_account_is_at_its_limit():
    """purchase-014 before purchase-015: a repeat of a finished form is never refused as rate-limited."""
    world, clock = World(), Clock()
    hub = coordinator(
        world, clock, idempotency=FakeIdempotency(), rate=FakeRate(clock), rate_limit_requests=2
    )
    first = hub.purchase(buy(key="a" * 32))  # request 1
    hub.start_checkout(buy(quantity=0, key="b" * 32))  # request 2: the limit is reached
    again = hub.purchase(buy(key="a" * 32))  # the same form again
    assert again.outcome is PurchaseOutcome.SUCCESS and again.replayed
    assert again.order.id == first.order.id
    assert len(world.orders) == 1


def test_a_rate_limited_form_can_be_used_once_the_minute_has_passed():
    """purchase-015: the key of a refused request is released, so it is not a conflict later."""
    world, clock = World(), Clock()
    hub = coordinator(
        world, clock, idempotency=FakeIdempotency(), rate=FakeRate(clock), rate_limit_requests=1
    )
    hub.start_checkout(buy(quantity=0, key="a" * 32))
    assert hub.purchase(buy(key="c" * 32)).outcome is PurchaseOutcome.RATE_LIMITED
    clock.value += timedelta(seconds=61)
    assert hub.purchase(buy(key="c" * 32)).outcome is PurchaseOutcome.SUCCESS


def test_requests_without_a_key_still_count_towards_the_limit():
    """purchase-015: a script cannot dodge the limit by leaving out the form key."""
    world, clock = World(), Clock()
    hub = coordinator(
        world, clock, idempotency=FakeIdempotency(), rate=FakeRate(clock), rate_limit_requests=2
    )
    outcomes = [hub.purchase(buy(key=None)).outcome for _ in range(3)]
    assert outcomes == [
        PurchaseOutcome.IDEMPOTENCY_KEY_REQUIRED,
        PurchaseOutcome.IDEMPOTENCY_KEY_REQUIRED,
        PurchaseOutcome.RATE_LIMITED,
    ]
