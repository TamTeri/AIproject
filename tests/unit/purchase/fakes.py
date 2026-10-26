"""In-memory fakes for every port the PurchaseCoordinator uses.

They behave like the PostgreSQL adapters (capacity, hold states, append-only
audit) so the purchase rules can be unit-tested with no database.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.inventory.models import Hold, HoldReleaseReason, HoldStatus
from app.orders.models import OrderSnapshot
from app.purchase.models import PaymentResult, PurchasePolicy, QuoteSnapshot
from app.purchase.service import PurchaseCoordinator

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@dataclass
class Tx:
    committed: bool = False
    rolled_back: bool = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class Transactions:
    def __init__(self) -> None:
        self.opened: list[Tx] = []

    def begin(self) -> Tx:
        tx = Tx()
        self.opened.append(tx)
        return tx


class Buyer:
    def __init__(self, buyer_id: str = "7") -> None:
        self.buyer_id = buyer_id

    def current_buyer_id(self, tx) -> str:
        return self.buyer_id


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.value = now

    def now(self, tx) -> datetime:
        return self.value


@dataclass
class World:
    """Shared state: events with capacity, holds, orders, audit rows."""

    capacity: dict[str, int] = field(default_factory=lambda: {"1": 10})
    holds: dict[str, Hold] = field(default_factory=dict)
    orders: list[OrderSnapshot] = field(default_factory=list)
    audit: list = field(default_factory=list)
    currencies: set[str] = field(default_factory=lambda: {"USD", "EUR"})

    def sold(self, event_id: str) -> int:
        return sum(o.quantity for o in self.orders if o.event_id == event_id)

    def held(self, event_id: str, now: datetime) -> int:
        return sum(
            h.quantity
            for h in self.holds.values()
            if h.event_id == event_id and h.status is HoldStatus.ACTIVE and h.expires_at > now
        )


class Events:
    def __init__(self, world: World) -> None:
        self.world = world

    def lock_event(self, tx, event_id: str) -> bool:
        return event_id in self.world.capacity


class Quotes:
    def __init__(self, world: World, unit_price_minor: int = 2500) -> None:
        self.world = world
        self.unit = unit_price_minor
        self.calls = 0

    def supported_currencies(self, tx) -> set[str]:
        return set(self.world.currencies)

    def quote(self, *, tx, buyer_id, event_id, quantity, currency) -> QuoteSnapshot:
        self.calls += 1
        return QuoteSnapshot(
            event_id=event_id,
            quantity=quantity,
            currency=currency,
            exchange_rate=Decimal("1"),
            total_minor=self.unit * quantity,
            unit_price_minor=self.unit,
            subtotal_minor=self.unit * quantity,
        )


class Inventory:
    def __init__(self, world: World, clock: Clock) -> None:
        self.world = world
        self.clock = clock
        self.next_id = 1

    def allocate_hold(self, *, tx, buyer_id, event_id, quantity, expires_at, quote_snapshot):
        now = self.clock.value
        available = self.world.capacity[event_id] - self.world.sold(event_id) - self.world.held(event_id, now)
        if available < quantity:
            return None
        hold = Hold(
            id=str(self.next_id),
            buyer_id=buyer_id,
            event_id=event_id,
            quantity=quantity,
            expires_at=expires_at,
            quote_snapshot=quote_snapshot,
        )
        self.next_id += 1
        self.world.holds[hold.id] = hold
        return hold

    def get_hold_for_buyer(self, *, tx, hold_id, buyer_id):
        hold = self.world.holds.get(str(hold_id))
        return hold if hold is not None and hold.buyer_id == buyer_id else None

    def convert_hold(self, *, tx, hold_id, buyer_id, now):
        hold = self.world.holds[hold_id]
        if hold.status is not HoldStatus.ACTIVE or hold.expires_at <= now:
            return None
        hold = replace(hold, status=HoldStatus.CONVERTED)
        self.world.holds[hold_id] = hold
        return hold

    def release_hold(self, *, tx, hold_id, buyer_id, reason, now):
        hold = self.world.holds[hold_id]
        if hold.status is HoldStatus.ACTIVE:
            hold = replace(hold, status=HoldReleaseReason(reason).status, release_reason=reason)
            self.world.holds[hold_id] = hold
        return hold


class Payments:
    def __init__(self) -> None:
        self.calls = 0

    def simulate(self, *, tx, buyer_id, hold, quote_snapshot, payment_choice="approve"):
        self.calls += 1
        if payment_choice == "decline":
            return PaymentResult(succeeded=False, reason_code="card_declined")
        return PaymentResult(succeeded=True, reason_code="OK")


class Orders:
    def __init__(self, world: World) -> None:
        self.world = world

    def create_order_snapshot(self, *, tx, buyer_id, hold, quote_snapshot):
        order = OrderSnapshot(
            id=str(len(self.world.orders) + 1),
            buyer_id=buyer_id,
            event_id=hold.event_id,
            hold_id=hold.id,
            quantity=hold.quantity,
            currency=quote_snapshot.currency,
            exchange_rate=quote_snapshot.exchange_rate,
            total_minor=quote_snapshot.total_minor,
            quote_snapshot=quote_snapshot,
        )
        self.world.orders.append(order)
        return order


class Audit:
    def __init__(self, world: World) -> None:
        self.world = world

    def append(self, *, tx, record) -> None:
        self.world.audit.append(record)


class Limits:
    def __init__(self, world: World, clock: Clock) -> None:
        self.world = world
        self.clock = clock

    def committed_quantity(self, tx, *, buyer_id, event_id) -> int:
        owned = sum(
            o.quantity for o in self.world.orders if o.buyer_id == buyer_id and o.event_id == event_id
        )
        held = sum(
            h.quantity
            for h in self.world.holds.values()
            if h.buyer_id == buyer_id
            and h.event_id == event_id
            and h.status is HoldStatus.ACTIVE
            and h.expires_at > self.clock.value
        )
        return owned + held


@dataclass
class Harness:
    world: World
    clock: Clock
    transactions: Transactions
    payments: Payments
    quotes: Quotes
    coordinator: PurchaseCoordinator

    def advance(self, minutes: int) -> None:
        self.clock.value += timedelta(minutes=minutes)


def make_harness(*, buyer_id: str = "7", world: World | None = None, clock: Clock | None = None) -> Harness:
    world = world or World()
    clock = clock or Clock()
    transactions = Transactions()
    payments = Payments()
    quotes = Quotes(world)
    coordinator = PurchaseCoordinator(
        transactions=transactions,
        identity=Buyer(buyer_id),
        database_time=clock,
        quotes=quotes,
        inventory=Inventory(world, clock),
        payments=payments,
        orders=Orders(world),
        audit=Audit(world),
        events=Events(world),
        limits=Limits(world, clock),
        policy=PurchasePolicy(hold_minutes=10, per_account_event_limit=4),
    )
    return Harness(world, clock, transactions, payments, quotes, coordinator)
