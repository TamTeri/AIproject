"""Feature adapters against real PostgreSQL: concurrency, holds, audit, ownership."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.purchase.models import PurchaseOutcome
from app.web.services import ServiceError
from app.wiring import build_services

pytestmark = pytest.mark.postgres

POETRY_SLAM = "6"  # seed: capacity 2
DEMO_NIGHT = "1"  # seed: capacity 100, 25.00 USD


def scalar(database, sql: str, **params):
    with database.engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def make_buyers(services, count: int, domain: str = "example.com") -> list[str]:
    ids = []
    for n in range(count):
        account = services.identity.register(
            name=f"Buyer {n}", email=f"buyer{n}@{domain}", password="password-123"
        )
        ids.append(account.account_id)
    return ids


def test_concurrent_buyers_never_oversell_the_last_tickets(seeded_database):
    services = build_services(seeded_database, environment="test")
    buyers = make_buyers(services, 10)

    def attempt(buyer_id: str):
        return services.purchase.quick_buy(buyer_id=buyer_id, event_id=POETRY_SLAM, currency="USD").outcome

    with ThreadPoolExecutor(max_workers=10) as pool:
        outcomes = list(pool.map(attempt, buyers))

    assert outcomes.count(PurchaseOutcome.SUCCESS) == 2
    assert outcomes.count(PurchaseOutcome.SOLD_OUT) == 8
    assert scalar(seeded_database, "SELECT COALESCE(SUM(quantity), 0) FROM orders WHERE event_id = 6") == 2
    assert (
        scalar(seeded_database, "SELECT available_quantity FROM event_availability WHERE event_id = 6") == 0
    )
    assert scalar(seeded_database, "SELECT count(*) FROM purchase_attempts") == 10


def test_concurrent_requests_from_one_buyer_respect_the_limit(seeded_database):
    services = build_services(seeded_database, environment="test")
    (buyer,) = make_buyers(services, 1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(
            pool.map(
                lambda _: (
                    services.purchase.quick_buy(buyer_id=buyer, event_id=DEMO_NIGHT, currency="USD").outcome
                ),
                range(8),
            )
        )

    assert outcomes.count(PurchaseOutcome.SUCCESS) == 4
    assert outcomes.count(PurchaseOutcome.LIMIT_EXCEEDED) == 4


def test_checkout_hold_then_pay_creates_order_with_snapshot(seeded_database):
    services = build_services(seeded_database, environment="test")
    (student,) = make_buyers(services, 1, domain="usf.edu")

    started = services.checkout.start(buyer_id=student, event_id=DEMO_NIGHT, quantity="2", currency="EUR")
    assert started.outcome is PurchaseOutcome.HOLD_CREATED
    assert scalar(seeded_database, "SELECT held_quantity FROM event_availability WHERE event_id = 1") == 2

    review = services.checkout.review(buyer_id=student, hold_id=started.hold.id)
    assert (review.total, review.discount) == ("41.40 EUR", "4.60 EUR")

    paid = services.checkout.pay(buyer_id=student, hold_id=started.hold.id, payment_choice="approve")
    assert paid.outcome is PurchaseOutcome.SUCCESS
    assert scalar(seeded_database, "SELECT sold_quantity FROM event_availability WHERE event_id = 1") == 2
    assert scalar(seeded_database, "SELECT held_quantity FROM event_availability WHERE event_id = 1") == 0
    assert scalar(seeded_database, "SELECT total_minor FROM orders") == 4140
    assert scalar(seeded_database, "SELECT rate_applied FROM orders") == Decimal("0.92")

    order = services.orders.get_for_buyer(buyer_id=student, order_id=paid.order.id)
    assert order.total == "41.40 EUR"


def test_rate_change_after_hold_does_not_change_the_price(seeded_database):
    services = build_services(seeded_database, environment="test")
    (buyer,) = make_buyers(services, 1)
    started = services.checkout.start(buyer_id=buyer, event_id=DEMO_NIGHT, quantity="1", currency="EUR")
    with seeded_database.engine.begin() as connection:
        connection.execute(text("UPDATE exchange_rates SET rate = 2 WHERE currency_code = 'EUR'"))
    paid = services.checkout.pay(buyer_id=buyer, hold_id=started.hold.id, payment_choice="approve")
    assert paid.order.total_minor == 2300  # 25.00 x 0.92, frozen at hold time


def test_expired_hold_is_released_and_cannot_be_paid(seeded_database):
    services = build_services(seeded_database, environment="test")
    (buyer,) = make_buyers(services, 1)
    started = services.checkout.start(buyer_id=buyer, event_id=POETRY_SLAM, quantity="2", currency="USD")
    with seeded_database.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE holds SET created_at = created_at - interval '11 minutes', expires_at = expires_at - interval '11 minutes'"
            )
        )
    assert (
        scalar(seeded_database, "SELECT available_quantity FROM event_availability WHERE event_id = 6") == 2
    )

    paid = services.checkout.pay(buyer_id=buyer, hold_id=started.hold.id, payment_choice="approve")

    assert paid.outcome is PurchaseOutcome.HOLD_EXPIRED
    assert scalar(seeded_database, "SELECT status FROM holds") == "expired"
    assert scalar(seeded_database, "SELECT count(*) FROM orders") == 0


def test_declined_payment_releases_hold_and_audits_failure(seeded_database):
    services = build_services(seeded_database, environment="test")
    (buyer,) = make_buyers(services, 1)
    started = services.checkout.start(buyer_id=buyer, event_id=POETRY_SLAM, quantity="2", currency="USD")

    paid = services.checkout.pay(buyer_id=buyer, hold_id=started.hold.id, payment_choice="decline")

    assert paid.outcome is PurchaseOutcome.PAYMENT_FAILED
    assert scalar(seeded_database, "SELECT status FROM holds") == "payment_failed"
    assert (
        scalar(seeded_database, "SELECT available_quantity FROM event_availability WHERE event_id = 6") == 2
    )
    assert (
        scalar(seeded_database, "SELECT outcome || ':' || reason_code FROM purchase_attempts")
        == "failed:payment_failed"
    )


def test_rejections_are_audited_with_raw_values(seeded_database):
    services = build_services(seeded_database, environment="test")
    (buyer,) = make_buyers(services, 1)
    services.checkout.start(buyer_id=buyer, event_id=DEMO_NIGHT, quantity="-5", currency="USD")
    services.checkout.start(buyer_id=buyer, event_id=DEMO_NIGHT, quantity="1", currency="XYZ")
    services.checkout.start(buyer_id=buyer, event_id="999", quantity="1", currency="USD")
    with seeded_database.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT reason_code, quantity_raw, currency_raw, event_id FROM purchase_attempts ORDER BY id"
            )
        ).all()
    assert [tuple(r) for r in rows] == [
        ("invalid_quantity", None, "USD", 1),
        ("unsupported_currency", 1, "XYZ", 1),
        ("event_not_found", 1, "USD", None),
    ]


def test_audit_table_is_append_only(seeded_database):
    services = build_services(seeded_database, environment="test")
    (buyer,) = make_buyers(services, 1)
    services.purchase.quick_buy(buyer_id=buyer, event_id=DEMO_NIGHT, currency="USD")
    for statement in ("UPDATE purchase_attempts SET outcome = 'failed'", "DELETE FROM purchase_attempts"):
        with pytest.raises(DBAPIError, match="append-only"):
            with seeded_database.engine.begin() as connection:
                connection.execute(text(statement))


def test_buyers_only_see_their_own_orders(seeded_database):
    services = build_services(seeded_database, environment="test")
    alice, bob = make_buyers(services, 2)
    order = services.purchase.quick_buy(buyer_id=alice, event_id=DEMO_NIGHT, currency="USD").order
    assert services.orders.get_for_buyer(buyer_id=alice, order_id=order.id) is not None
    assert services.orders.get_for_buyer(buyer_id=bob, order_id=order.id) is None
    assert services.orders.list_for_buyer(buyer_id=bob) == []


def test_registration_login_and_session_timeout(seeded_database):
    services = build_services(seeded_database, environment="test")
    services.identity.register(name="Ada", email="Ada@USF.edu", password="password-123")
    with pytest.raises(ServiceError) as duplicate:
        services.identity.register(name="Ada", email="ada@usf.edu", password="password-123")
    assert duplicate.value.status_code == 409
    assert scalar(seeded_database, "SELECT password_hash LIKE 'pbkdf2_sha256$%' FROM accounts") is True

    principal = services.identity.authenticate(email="ada@usf.edu", password="password-123")
    token = services.identity.start_session(account_id=principal.account_id)
    assert services.identity.resolve_session(token=token).email == "ada@usf.edu"

    with seeded_database.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE account_sessions SET created_at = created_at - interval '31 minutes', last_seen_at = last_seen_at - interval '31 minutes'"
            )
        )
    assert services.identity.resolve_session(token=token) is None


def test_admin_rate_update_is_validated_and_applies_to_new_quotes(seeded_database):
    services = build_services(seeded_database, environment="test")
    (buyer,) = make_buyers(services, 1)
    with seeded_database.engine.begin() as connection:
        connection.execute(text("UPDATE accounts SET role = 'administrator'"))
    admin = services.identity.authenticate(email="buyer0@example.com", password="password-123")

    services.admin.set_rate(actor=admin, currency="EUR", rate="0.5")
    with pytest.raises(ServiceError):
        services.admin.set_rate(actor=admin, currency="EUR", rate="0")

    order = services.purchase.quick_buy(buyer_id=buyer, event_id=DEMO_NIGHT, currency="EUR").order
    assert order.total_minor == 1250
    page = services.admin.audit_page(actor=admin)
    assert page.rows[0].buyer_email == "buyer0@example.com"


def test_production_environment_fails_closed_for_pricing(seeded_database):
    services = build_services(seeded_database, environment="development")
    assert services.pricing.currencies()  # local/dev works
    import os

    os.environ["EVENTHUB_SESSION_IDLE_TIMEOUT_SECONDS"] = "1800"
    try:
        locked = build_services(seeded_database, environment="production")
    finally:
        del os.environ["EVENTHUB_SESSION_IDLE_TIMEOUT_SECONDS"]
    with pytest.raises(ServiceError) as unavailable:
        locked.purchase.quick_buy(buyer_id="1", event_id=DEMO_NIGHT, currency="USD")
    assert unavailable.value.status_code == 503
