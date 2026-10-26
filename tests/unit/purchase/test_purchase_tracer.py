from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.purchase.models import PurchaseRequest, QuoteSnapshot
from app.purchase.service import PurchaseCoordinator


@dataclass
class FakeTransaction:
    commits: int = 0
    rollbacks: int = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def execute(self, statement: str, parameters=None):  # pragma: no cover - interface seam
        return None

    def fetch_one(self, statement: str, parameters=None):  # pragma: no cover - interface seam
        return None

    def fetch_all(self, statement: str, parameters=None):  # pragma: no cover - interface seam
        return []


class FakeTransactions:
    def __init__(self) -> None:
        self.contexts: list[FakeTransaction] = []

    def begin(self) -> FakeTransaction:
        context = FakeTransaction()
        self.contexts.append(context)
        return context


class FakeIdentity:
    def __init__(self, buyer_id: str) -> None:
        self.buyer_id = buyer_id
        self.calls: list[FakeTransaction] = []

    def current_buyer_id(self, tx: FakeTransaction) -> str:
        self.calls.append(tx)
        return self.buyer_id


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.value = now
        self.calls: list[FakeTransaction] = []

    def now(self, tx: FakeTransaction) -> datetime:
        self.calls.append(tx)
        return self.value


class FakeQuotes:
    def __init__(self) -> None:
        self.calls: list[tuple[FakeTransaction, str, str, int, str]] = []

    def supported_currencies(self, tx) -> set[str]:
        return {"USD"}

    def quote(self, *, tx, buyer_id, event_id, quantity, currency) -> QuoteSnapshot:
        self.calls.append((tx, buyer_id, event_id, quantity, currency))
        return QuoteSnapshot(
            event_id=event_id,
            quantity=quantity,
            currency=currency,
            exchange_rate=Decimal("1"),
            total_minor=2500,
            unit_price_minor=2500,
        )


class FakeInventory:
    def __init__(self) -> None:
        self.next_hold = 1
        self.holds: dict[str, SimpleNamespace] = {}
        self.allocate_calls: list[tuple] = []
        self.convert_calls: list[tuple] = []
        self.release_calls: list[tuple] = []

    def allocate_hold(self, *, tx, buyer_id, event_id, quantity, expires_at, quote_snapshot):
        self.allocate_calls.append((tx, buyer_id, event_id, quantity, expires_at, quote_snapshot))
        hold = SimpleNamespace(
            id=f"hold-{self.next_hold}",
            buyer_id=buyer_id,
            event_id=event_id,
            quantity=quantity,
            expires_at=expires_at,
            status="active",
            release_reason=None,
            quote_snapshot=quote_snapshot,
        )
        self.next_hold += 1
        self.holds[hold.id] = hold
        return hold

    def get_hold_for_buyer(self, *, tx, hold_id, buyer_id):
        hold = self.holds.get(hold_id)
        if hold is None or hold.buyer_id != buyer_id:
            return None
        return hold

    def convert_hold(self, *, tx, hold_id, buyer_id, now):
        self.convert_calls.append((tx, hold_id, buyer_id, now))
        hold = self.holds[hold_id]
        hold.status = "converted"
        return hold

    def release_hold(self, *, tx, hold_id, buyer_id, reason, now):  # pragma: no cover - later slice
        self.release_calls.append((tx, hold_id, buyer_id, reason, now))
        hold = self.holds[hold_id]
        hold.status = "released"
        hold.release_reason = reason
        return hold


class FakePayments:
    def __init__(self, succeeded: bool = True) -> None:
        self.succeeded = succeeded
        self.calls: list[tuple] = []

    def simulate(self, *, tx, buyer_id, hold, quote_snapshot, payment_choice="approve"):
        self.calls.append((tx, buyer_id, hold, quote_snapshot))
        return SimpleNamespace(succeeded=self.succeeded, reason_code="PAYMENT_FAILED")


class FakeOrders:
    def __init__(self) -> None:
        self.orders: list[SimpleNamespace] = []

    def create_order_snapshot(self, *, tx, buyer_id, hold, quote_snapshot):
        order = SimpleNamespace(
            id=f"order-{len(self.orders) + 1}",
            buyer_id=buyer_id,
            event_id=hold.event_id,
            hold_id=hold.id,
            quantity=hold.quantity,
            currency=quote_snapshot.currency,
            exchange_rate=quote_snapshot.exchange_rate,
            total_minor=quote_snapshot.total_minor,
            quote_snapshot=quote_snapshot,
        )
        self.orders.append(order)
        return order


class FakeEvents:
    def lock_event(self, tx, event_id):
        return True


class FakeLimits:
    def committed_quantity(self, tx, *, buyer_id, event_id):
        return 0


class FakeAudit:
    def __init__(self) -> None:
        self.records: list = []

    def append(self, *, tx, record) -> None:
        self.records.append(record)


def test_successful_purchase_creates_order_without_second_inventory_allocation() -> None:
    transactions = FakeTransactions()
    identity = FakeIdentity("buyer-a")
    clock = FakeClock(datetime(2026, 10, 26, 12, 0, tzinfo=UTC))
    quotes = FakeQuotes()
    inventory = FakeInventory()
    payments = FakePayments(succeeded=True)
    orders = FakeOrders()
    audit = FakeAudit()

    service = PurchaseCoordinator(
        transactions=transactions,
        identity=identity,
        database_time=clock,
        quotes=quotes,
        inventory=inventory,
        payments=payments,
        orders=orders,
        audit=audit,
        events=FakeEvents(),
        limits=FakeLimits(),
    )

    result = service.purchase(
        PurchaseRequest(event_id="event-1", quantity=1, currency="USD", request_id="req-1")
    )

    assert result.outcome == "success"
    assert result.order is orders.orders[0]
    assert result.order.buyer_id == "buyer-a"
    assert result.order.event_id == "event-1"
    assert result.order.quantity == 1
    assert result.order.currency == "USD"
    assert result.order.exchange_rate == Decimal("1")
    assert result.order.total_minor == 2500
    assert inventory.holds[result.hold.id].status == "converted"
    assert len(inventory.allocate_calls) == 1
    assert len(inventory.convert_calls) == 1
    assert len(inventory.release_calls) == 0
    assert len(orders.orders) == 1
    assert len(audit.records) == 1
    assert audit.records[0].outcome == "success"
    assert audit.records[0].buyer_id == "buyer-a"
    assert audit.records[0].event_id == "event-1"
    assert audit.records[0].quantity == 1
    assert audit.records[0].currency == "USD"
    assert transactions.contexts[0].commits == 1
    assert transactions.contexts[0].rollbacks == 0
    assert identity.calls == [transactions.contexts[0]]
    assert clock.calls == [transactions.contexts[0]]
    assert quotes.calls[0][0] is transactions.contexts[0]
    assert inventory.allocate_calls[0][0] is transactions.contexts[0]
    assert payments.calls[0][0] is transactions.contexts[0]
    assert orders.orders[0] is result.order
