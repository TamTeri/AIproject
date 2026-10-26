"""Purchase rules: validation, limits, sold out, holds, payment, audit.

Requirements: purchase-001..011, inventory-002/005/006, audit-001/002/004.
"""

from __future__ import annotations

import pytest

from app.inventory.models import HoldStatus
from app.purchase.models import PaymentRequest, PurchaseOutcome, PurchaseRequest
from app.purchase.service import parse_currency, parse_quantity
from tests.unit.purchase.fakes import World, make_harness


def request(quantity: object = 1, currency: object = "USD", event_id: str = "1") -> PurchaseRequest:
    return PurchaseRequest(event_id=event_id, quantity=quantity, currency=currency)


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize("raw", [0, -1, "0", "-2", "abc", "1.5", "", None, True, 1001, "99999999"])
def test_parse_quantity_rejects_invalid_values(raw):
    assert parse_quantity(raw) is None


@pytest.mark.parametrize(("raw", "expected"), [(1, 1), ("3", 3), (" 2 ", 2), (1000, 1000)])
def test_parse_quantity_accepts_whole_positive_numbers(raw, expected):
    assert parse_quantity(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [("usd", "USD"), (" EUR ", "EUR"), ("US", None), ("U5D", None), (7, None)]
)
def test_parse_currency_normalizes_or_rejects(raw, expected):
    assert parse_currency(raw) == expected


@pytest.mark.parametrize("quantity", [0, -3, "two", "1.5"])
def test_invalid_quantity_is_rejected_and_audited(quantity):
    h = make_harness()
    result = h.coordinator.start_checkout(request(quantity=quantity))

    assert result.outcome is PurchaseOutcome.INVALID_QUANTITY
    assert result.hold is None
    assert h.world.holds == {}
    assert len(h.world.audit) == 1
    record = h.world.audit[0]
    assert (record.outcome, record.reason_code) == ("rejected", "invalid_quantity")
    assert h.transactions.opened[0].committed  # the audit row is kept


def test_unsupported_currency_is_rejected_before_quantity():
    h = make_harness()
    result = h.coordinator.start_checkout(request(quantity=0, currency="XYZ"))
    assert result.outcome is PurchaseOutcome.UNSUPPORTED_CURRENCY
    assert h.world.audit[0].reason_code == "unsupported_currency"
    assert h.world.audit[0].currency == "XYZ"


def test_unknown_event_is_rejected_without_referencing_it_in_audit():
    h = make_harness()
    result = h.coordinator.start_checkout(request(event_id="999"))
    assert result.outcome is PurchaseOutcome.EVENT_NOT_FOUND
    assert h.world.audit[0].event_id is None  # no dangling foreign key


# ------------------------------------------------------- holds and inventory


def test_start_checkout_creates_ten_minute_hold_and_reserves_tickets():
    h = make_harness()
    result = h.coordinator.start_checkout(request(quantity=3))

    assert result.outcome is PurchaseOutcome.HOLD_CREATED
    assert result.hold.quantity == 3
    assert (result.hold.expires_at - h.clock.value).total_seconds() == 600
    assert h.world.held("1", h.clock.value) == 3
    assert h.world.audit == []  # holding is not yet a purchase attempt outcome


def test_sold_out_when_not_enough_tickets_left():
    world = World(capacity={"1": 2})
    h = make_harness(world=world)
    result = h.coordinator.start_checkout(request(quantity=3))
    assert result.outcome is PurchaseOutcome.SOLD_OUT
    assert world.audit[0].reason_code == "sold_out"


def test_two_buyers_never_get_the_same_last_ticket():
    world = World(capacity={"1": 1})
    first = make_harness(buyer_id="1", world=world)
    second = make_harness(buyer_id="2", world=world, clock=first.clock)

    assert first.coordinator.purchase(request()).outcome is PurchaseOutcome.SUCCESS
    assert second.coordinator.purchase(request()).outcome is PurchaseOutcome.SOLD_OUT
    assert world.sold("1") == 1


def test_expired_hold_releases_tickets_and_cannot_be_paid():
    h = make_harness()
    hold = h.coordinator.start_checkout(request(quantity=2)).hold
    h.advance(minutes=11)

    result = h.coordinator.pay(PaymentRequest(hold_id=hold.id))

    assert result.outcome is PurchaseOutcome.HOLD_EXPIRED
    assert h.world.holds[hold.id].status is HoldStatus.EXPIRED
    assert h.world.orders == []
    assert h.payments.calls == 0
    assert h.world.audit[-1].reason_code == "hold_expired"


def test_expired_holds_do_not_count_against_availability():
    world = World(capacity={"1": 2})
    h = make_harness(world=world)
    h.coordinator.start_checkout(request(quantity=2))
    h.advance(minutes=10)
    assert h.coordinator.start_checkout(request(quantity=2)).outcome is PurchaseOutcome.HOLD_CREATED


# ------------------------------------------------------------------- payment


def test_pay_converts_hold_without_second_inventory_subtraction():
    world = World(capacity={"1": 4})
    h = make_harness(world=world)
    hold = h.coordinator.start_checkout(request(quantity=4)).hold

    result = h.coordinator.pay(PaymentRequest(hold_id=hold.id))

    assert result.outcome is PurchaseOutcome.SUCCESS
    assert world.holds[hold.id].status is HoldStatus.CONVERTED
    assert world.sold("1") == 4  # 4 sold, 0 held: capacity not double-counted
    assert world.held("1", h.clock.value) == 0
    assert result.order.total_minor == 4 * 2500
    record = world.audit[-1]
    assert (record.outcome, record.reason_code, record.order_id) == ("success", "success", result.order.id)
    assert (record.buyer_id, record.event_id, record.quantity, record.currency) == ("7", "1", 4, "USD")


def test_order_uses_price_frozen_at_hold_time():
    h = make_harness()
    hold = h.coordinator.start_checkout(request(quantity=1)).hold
    h.quotes.unit = 9999  # e.g. admin changed a rate after the hold was placed
    result = h.coordinator.pay(PaymentRequest(hold_id=hold.id))
    assert result.order.total_minor == 2500


def test_declined_payment_releases_hold_exactly_once_and_creates_no_order():
    h = make_harness()
    hold = h.coordinator.start_checkout(request(quantity=2)).hold

    result = h.coordinator.pay(PaymentRequest(hold_id=hold.id, payment_choice="decline"))
    again = h.coordinator.pay(PaymentRequest(hold_id=hold.id))

    assert result.outcome is PurchaseOutcome.PAYMENT_FAILED
    assert h.world.holds[hold.id].status is HoldStatus.PAYMENT_FAILED
    assert again.outcome is PurchaseOutcome.HOLD_TERMINAL
    assert h.world.orders == []
    assert [r.outcome for r in h.world.audit] == ["failed", "rejected"]
    assert h.world.held("1", h.clock.value) == 0


def test_buyer_cannot_pay_for_someone_elses_hold():
    world = World()
    owner = make_harness(buyer_id="1", world=world)
    thief = make_harness(buyer_id="2", world=world, clock=owner.clock)
    hold = owner.coordinator.start_checkout(request()).hold

    result = thief.coordinator.pay(PaymentRequest(hold_id=hold.id))

    assert result.outcome is PurchaseOutcome.HOLD_NOT_FOUND
    assert world.orders == []


def test_cancel_releases_tickets():
    h = make_harness()
    hold = h.coordinator.start_checkout(request(quantity=2)).hold
    result = h.coordinator.cancel(hold.id)
    assert result.outcome is PurchaseOutcome.CANCELLED
    assert h.world.holds[hold.id].status is HoldStatus.CANCELLED
    assert h.world.held("1", h.clock.value) == 0


# -------------------------------------------------------------------- limits


def test_purchase_limit_counts_owned_and_held_tickets():
    h = make_harness()
    assert h.coordinator.purchase(request(quantity=3)).outcome is PurchaseOutcome.SUCCESS
    assert h.coordinator.start_checkout(request(quantity=1)).outcome is PurchaseOutcome.HOLD_CREATED

    result = h.coordinator.start_checkout(request(quantity=1))

    assert result.outcome is PurchaseOutcome.LIMIT_EXCEEDED
    assert h.world.audit[-1].reason_code == "limit_exceeded"


def test_limit_is_per_event():
    world = World(capacity={"1": 10, "2": 10})
    h = make_harness(world=world)
    assert h.coordinator.purchase(request(quantity=4, event_id="1")).outcome is PurchaseOutcome.SUCCESS
    assert h.coordinator.purchase(request(quantity=4, event_id="2")).outcome is PurchaseOutcome.SUCCESS


# ------------------------------------------------------------- quick buy path


def test_quick_buy_uses_the_same_validation_as_checkout():
    h = make_harness()
    result = h.coordinator.purchase(request(quantity=1, currency="GBP"))  # not enabled
    assert result.outcome is PurchaseOutcome.UNSUPPORTED_CURRENCY
    assert h.world.orders == []


def test_every_attempt_is_audited_with_required_fields():
    h = make_harness()
    h.coordinator.purchase(request(quantity=1))
    h.coordinator.purchase(request(quantity=-1))
    h.coordinator.purchase(request(currency="XYZ"))
    assert len(h.world.audit) == 3
    for record in h.world.audit:
        assert record.submitted_at is not None
        assert record.buyer_id == "7"
        assert record.outcome in {"success", "rejected", "failed"}


# ------------------------------------------------------------ internal errors


class ExplodingOrders:
    def create_order_snapshot(self, **_):
        raise RuntimeError("database went away")


def test_unexpected_error_rolls_back_and_still_leaves_an_audit_record():
    h = make_harness()
    h.coordinator._orders = ExplodingOrders()

    with pytest.raises(RuntimeError):
        h.coordinator.purchase(request())

    assert h.transactions.opened[0].rolled_back
    assert h.transactions.opened[1].committed
    assert h.world.audit[-1].reason_code == "internal_error"
    assert h.world.audit[-1].hold_id is None
