"""Call 5 behaviour against real PostgreSQL (row locks, unique keys, real time).

inventory-009: Thuy's last-ticket race, repeated 200 times. Priya: "Keep it
forever; it's exactly the kind that quietly starts failing after someone
reorganizes the code." Set EVENTHUB_RACE_REPEATS to change the count.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.purchase.models import PurchaseOutcome
from app.wiring import build_services

pytestmark = pytest.mark.postgres

RACE_REPEATS = int(os.environ.get("EVENTHUB_RACE_REPEATS", "200"))


def key() -> str:
    return uuid4().hex


def scalar(database, sql: str, **params):
    with database.engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def new_event(database, *, capacity: int, starts_in: str = "30 days", price_minor: int = 2000) -> str:
    with database.engine.begin() as connection:
        return str(
            connection.execute(
                text(
                    f"""
                    INSERT INTO events (catalog_key, title, artist, venue, starts_at, host_type,
                                        base_price_minor, capacity)
                    VALUES (:key, 'Race', 'Race Band', 'Hall', CURRENT_TIMESTAMP + INTERVAL '{starts_in}',
                            'usf', :price, :capacity)
                    RETURNING id
                    """
                ),
                {"key": f"race-{uuid4().hex}", "capacity": capacity, "price": price_minor},
            ).scalar_one()
        )


def buyers(services, count: int, domain: str = "example.com") -> list[str]:
    return [
        services.identity.register(
            name=f"Buyer {n}", email=f"{uuid4().hex[:10]}@{domain}", password="password-123"
        ).account_id
        for n in range(count)
    ]


def quick_accounts(database, count: int) -> list[str]:
    """Accounts inserted directly (no password hashing), so 400 buyers take a moment, not minutes."""
    with database.engine.begin() as connection:
        return [
            str(
                connection.execute(
                    text(
                        "INSERT INTO accounts (name, normalized_email, password_hash) "
                        "VALUES ('Racer', :email, 'not-a-login') RETURNING id"
                    ),
                    {"email": f"racer-{uuid4().hex}@example.com"},
                ).scalar_one()
            )
            for _ in range(count)
        ]


def test_last_ticket_race_repeated_200_times(seeded_database):
    """inventory-009: two buyers, one ticket, same moment: exactly one success, every time.

    Each round uses two new buyers. (The first version reused the same two for
    all 200 rounds; once purchase-015 limited each account to 10 requests a
    minute, rounds 11+ were correctly refused as rate_limited.)
    """
    services = build_services(seeded_database, environment="test")
    tally = {"success": 0, "sold_out": 0}
    for _ in range(RACE_REPEATS):
        alice, bob = quick_accounts(seeded_database, 2)
        event_id = new_event(seeded_database, capacity=1)
        start = threading.Barrier(2)

        def attempt(buyer_id: str, event_id: str = event_id, start: threading.Barrier = start):
            start.wait()
            return services.purchase.quick_buy(
                buyer_id=buyer_id, event_id=event_id, currency="USD", idempotency_key=key()
            ).outcome

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(pool.map(attempt, [alice, bob]))
        assert outcomes == [PurchaseOutcome.SOLD_OUT, PurchaseOutcome.SUCCESS], outcomes
        assert (
            scalar(seeded_database, "SELECT COUNT(*) FROM orders WHERE event_id = :e", e=int(event_id)) == 1
        )
        tally["success"] += 1
        tally["sold_out"] += 1
    assert tally == {"success": RACE_REPEATS, "sold_out": RACE_REPEATS}


def test_same_form_key_sent_five_times_at_once_creates_one_order(seeded_database):
    """purchase-014: the primary key makes the copies wait, then replay the first result."""
    services = build_services(seeded_database, environment="test")
    (buyer,) = buyers(services, 1)
    event_id = new_event(seeded_database, capacity=10)
    form_key = key()
    start = threading.Barrier(5)

    def submit(_):
        start.wait()
        return services.purchase.quick_buy(
            buyer_id=buyer, event_id=event_id, currency="USD", idempotency_key=form_key
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(submit, range(5)))

    assert {r.outcome for r in results} == {PurchaseOutcome.SUCCESS}
    assert len({r.order.id for r in results}) == 1
    assert sum(r.replayed for r in results) == 4
    assert scalar(seeded_database, "SELECT COUNT(*) FROM orders WHERE event_id = :e", e=int(event_id)) == 1
    reasons = scalar(
        seeded_database,
        "SELECT string_agg(reason_code, ',' ORDER BY reason_code) FROM purchase_attempts WHERE event_id = :e",
        e=int(event_id),
    )
    assert reasons == "replayed,replayed,replayed,replayed,success"


def test_eleventh_request_in_a_minute_is_rate_limited(seeded_database):
    """purchase-015: the counter row is shared by every web worker, so the limit holds."""
    services = build_services(seeded_database, environment="test")
    (buyer,) = buyers(services, 1)
    event_id = new_event(seeded_database, capacity=10)

    def start(quantity: str = "0"):
        return services.checkout.start(
            buyer_id=buyer, event_id=event_id, quantity=quantity, currency="USD", idempotency_key=key()
        ).outcome

    with ThreadPoolExecutor(max_workers=10) as pool:
        first_ten = list(pool.map(lambda _: start(), range(10)))
    assert set(first_ten) == {PurchaseOutcome.QUANTITY_ZERO}
    assert start("1") is PurchaseOutcome.RATE_LIMITED

    with seeded_database.engine.begin() as connection:  # the minute passes
        connection.execute(
            text(
                "UPDATE purchase_rate_windows SET window_started_at = window_started_at - INTERVAL '61 seconds'"
            )
        )
    assert start("1") is PurchaseOutcome.HOLD_CREATED


def test_email_change_removes_the_discount_even_for_an_open_hold(seeded_database):
    """pricing-011 + identity-014: Kenji's finding, end to end in the database."""
    services = build_services(seeded_database, environment="test")
    (kenji,) = buyers(services, 1, domain="usf.edu")
    event_id = new_event(seeded_database, capacity=5, price_minor=2000)

    hold = services.checkout.start(
        buyer_id=kenji, event_id=event_id, quantity="2", currency="USD", idempotency_key=key()
    ).hold
    assert services.checkout.review(buyer_id=kenji, hold_id=hold.id).total == "36.00 USD"  # 10% off

    services.identity.change_email(
        account_id=kenji, new_email=f"{uuid4().hex[:8]}@gmail.com", current_password="password-123"
    )
    paid = services.checkout.pay(
        buyer_id=kenji, hold_id=hold.id, payment_choice="approve", idempotency_key=key()
    )
    assert paid.outcome is PurchaseOutcome.ELIGIBILITY_CHANGED
    assert scalar(seeded_database, "SELECT status FROM holds WHERE id = :h", h=int(hold.id)) == "cancelled"
    assert scalar(seeded_database, "SELECT COUNT(*) FROM orders WHERE event_id = :e", e=int(event_id)) == 0

    fresh = services.checkout.start(
        buyer_id=kenji, event_id=event_id, quantity="2", currency="USD", idempotency_key=key()
    )
    assert services.checkout.review(buyer_id=kenji, hold_id=fresh.hold.id).total == "40.00 USD"


def test_events_that_have_started_are_not_sold(seeded_database):
    """purchase-018: sales close at the start time; the catalog says so too."""
    services = build_services(seeded_database, environment="test")
    (buyer,) = buyers(services, 1)
    past = new_event(seeded_database, capacity=5, starts_in="-1 hour")
    result = services.purchase.quick_buy(buyer_id=buyer, event_id=past, currency="USD", idempotency_key=key())
    assert result.outcome is PurchaseOutcome.SALES_CLOSED
    assert services.catalog.get_event(event_id=past).sales_closed is True
    upcoming = new_event(seeded_database, capacity=5, starts_in="5 minutes")
    assert services.catalog.get_event(event_id=upcoming).sales_closed is False


def test_not_logged_in_attempt_is_recorded_without_a_buyer(seeded_database):
    """purchase-016 / audit-008."""
    services = build_services(seeded_database, environment="test")
    services.checkout.record_unauthenticated(event_id="1", quantity="2", currency="EUR")
    row = None
    with seeded_database.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT buyer_id, event_id, quantity_raw, currency_raw, outcome, reason_code FROM purchase_attempts"
            )
        ).one()
    assert tuple(row) == (None, 1, 2, "EUR", "rejected", "not_authenticated")


def test_registration_saves_the_chosen_home_currency(seeded_database):
    """identity-015."""
    services = build_services(seeded_database, environment="test")
    account = services.identity.register(
        name="Intl", email=f"{uuid4().hex[:8]}@example.com", password="password-123", currency="gbp"
    )
    assert (
        scalar(
            seeded_database,
            "SELECT preferred_currency FROM accounts WHERE id = :a",
            a=int(account.account_id),
        )
        == "GBP"
    )


def test_expired_form_keys_are_cleaned_up(seeded_database):
    """purchase-014: keys older than the retention window are removed when the buyer claims a new one."""
    services = build_services(seeded_database, environment="test")
    (buyer,) = buyers(services, 1)
    old_key = key()
    services.purchase.quick_buy(buyer_id=buyer, event_id="1", currency="USD", idempotency_key=old_key)
    with seeded_database.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE idempotency_records SET created_at = created_at - INTERVAL '25 hours', "
                "expires_at = expires_at - INTERVAL '25 hours', completed_at = completed_at - INTERVAL '25 hours'"
            )
        )
    services.purchase.quick_buy(buyer_id=buyer, event_id="1", currency="USD", idempotency_key=key())
    remaining = scalar(
        seeded_database,
        "SELECT COUNT(*) FROM idempotency_records WHERE buyer_id = :b AND idempotency_key = :k",
        b=int(buyer),
        k=old_key,
    )
    assert remaining == 0
