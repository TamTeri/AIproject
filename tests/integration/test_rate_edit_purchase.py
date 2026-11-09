"""Call 6: an admin rate edit is what the next purchase uses (admin-006, pricing-013).

Needs PostgreSQL (EVENTHUB_TEST_DATABASE_URL); skipped otherwise.
Event 1 costs 25.00 USD; JPY has no minor unit, so 25 USD at rate R is 25 * R yen.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.purchase.models import PurchaseOutcome
from app.web.services import ServiceError
from app.wiring import build_services

pytestmark = pytest.mark.postgres

EVENT = "1"


def key() -> str:
    return uuid4().hex


def scalar(database, sql: str, **params):
    with database.engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


@pytest.fixture
def world(seeded_database):
    """JPY at 150 (created here if the seed has no JPY), one buyer, one administrator."""
    with seeded_database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO currencies (code, minor_unit, enabled) VALUES ('JPY', 0, TRUE) ON CONFLICT DO NOTHING"
            )
        )
        connection.execute(
            text(
                "INSERT INTO exchange_rates (currency_code, rate) VALUES ('JPY', 150) "
                "ON CONFLICT (currency_code) DO UPDATE SET rate = 150"
            )
        )
    services = build_services(seeded_database, environment="test")
    buyer = services.identity.register(name="Buyer", email="buyer@example.com", password="password-123")
    services.identity.register(name="Admin", email="admin@example.com", password="password-123")
    with seeded_database.engine.begin() as connection:
        connection.execute(
            text("UPDATE accounts SET role = 'administrator' WHERE normalized_email = 'admin@example.com'")
        )
    admin = services.identity.authenticate(email="admin@example.com", password="password-123")
    return seeded_database, services, admin, buyer.account_id


@pytest.mark.requirement("admin-006", "pricing-013")
def test_next_purchase_uses_the_edited_jpy_rate_and_history_is_written(world):
    db, services, admin, buyer = world
    services.admin.set_rate(actor=admin, currency="JPY", rate="140")  # -6.7%: no confirmation needed

    result = services.purchase.quick_buy(
        idempotency_key=key(), buyer_id=buyer, event_id=EVENT, currency="JPY"
    )
    assert result.outcome is PurchaseOutcome.SUCCESS
    assert scalar(db, "SELECT total_minor FROM orders") == 3500
    assert scalar(db, "SELECT rate_applied FROM orders") == Decimal("140")

    with db.engine.connect() as connection:
        row = connection.execute(
            text("SELECT old_rate, new_rate, changed_by FROM exchange_rate_history WHERE currency = 'JPY'")
        ).one()
    assert (row.old_rate, row.new_rate) == (Decimal("150"), Decimal("140"))
    assert row.changed_by is not None


@pytest.mark.requirement("admin-006")
def test_ten_times_typo_is_refused_unless_confirmed(world):
    db, services, admin, _buyer = world
    with pytest.raises(ServiceError, match="25%"):
        services.admin.set_rate(actor=admin, currency="JPY", rate="15")
    assert scalar(db, "SELECT rate FROM exchange_rates WHERE currency_code = 'JPY'") == Decimal("150")
    assert scalar(db, "SELECT count(*) FROM exchange_rate_history") == 0

    services.admin.set_rate(actor=admin, currency="JPY", rate="15", confirm_large_change=True)
    assert scalar(db, "SELECT rate FROM exchange_rates WHERE currency_code = 'JPY'") == Decimal("15")
    assert scalar(db, "SELECT count(*) FROM exchange_rate_history") == 1


@pytest.mark.requirement("pricing-013")
def test_held_price_stays_frozen_when_the_rate_is_edited_before_payment(world):
    db, services, admin, buyer = world
    started = services.checkout.start(
        idempotency_key=key(), buyer_id=buyer, event_id=EVENT, quantity="1", currency="JPY"
    )
    assert started.outcome is PurchaseOutcome.HOLD_CREATED

    services.admin.set_rate(actor=admin, currency="JPY", rate="160")  # +6.7%
    paid = services.checkout.pay(
        idempotency_key=key(), buyer_id=buyer, hold_id=started.hold.id, payment_choice="approve"
    )
    assert paid.outcome is PurchaseOutcome.SUCCESS
    assert scalar(db, "SELECT total_minor FROM orders") == 3750  # 25 x 150, not 25 x 160
    assert scalar(db, "SELECT rate_applied FROM orders") == Decimal("150")


@pytest.mark.requirement("admin-006")
def test_database_rejects_a_zero_rate_even_via_direct_sql(world):
    db = world[0]
    with pytest.raises(IntegrityError), db.engine.begin() as connection:
        connection.execute(text("UPDATE exchange_rates SET rate = 0 WHERE currency_code = 'JPY'"))
