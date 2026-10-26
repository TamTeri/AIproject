"""The final application (create_app) end to end against PostgreSQL."""

from __future__ import annotations

import re

import pytest

from app import create_app

pytestmark = pytest.mark.postgres

TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


def csrf(client, path: str) -> str:
    return TOKEN.search(client.get(path).get_data(as_text=True)).group(1)


@pytest.fixture
def app(seeded_database, database_url):
    return create_app(
        {"TESTING": True, "SECRET_KEY": "e2e", "DATABASE_URL": database_url, "EVENTHUB_ENVIRONMENT": "test"}
    )


def register_and_login(client, email: str, password: str = "password-123") -> str:
    client.post(
        "/register",
        data={"csrf_token": csrf(client, "/register"), "name": "Fan", "email": email, "password": password},
    )
    client.post("/login", data={"csrf_token": csrf(client, "/login"), "email": email, "password": password})
    return csrf(client, "/events")


def test_student_buys_tickets_and_reopens_the_confirmation(app):
    client = app.test_client()

    # identity-008: asking for order history first sends you to login and back
    assert client.get("/orders").location == "/login?next=/orders"
    token = register_and_login(client, "Student@USF.edu")

    search = client.get("/events?q=jazz").get_data(as_text=True)
    assert "Bulls Jazz Ensemble" in search and "Tampa Symphony" not in search

    start = client.post("/events/2/checkout", data={"csrf_token": token, "quantity": "2", "currency": "GBP"})
    review = client.get(start.location).get_data(as_text=True)
    # 2 x 15.00 USD = 30.00 -> 10% student discount = 27.00 -> x0.79 = 21.33 GBP
    assert "21.33 GBP" in review and "−2.37 GBP" in review

    paid = client.post(start.location + "/pay", data={"csrf_token": token, "payment": "approve"})
    confirmation = client.get(paid.location).get_data(as_text=True)
    assert "Order confirmed" in confirmation and "21.33 GBP" in confirmation and "0.79" in confirmation

    history = client.get("/orders").get_data(as_text=True)
    order_link = re.search(r'href="(/orders/\d+)"', history).group(1)
    reopened = client.get(order_link).get_data(as_text=True)
    assert "21.33 GBP" in reopened  # orders-004: reopen any time


def test_quick_buy_uses_saved_currency(app):
    client = app.test_client()
    token = register_and_login(client, "fan@example.com")
    client.post("/account", data={"csrf_token": token, "currency": "CAD"})

    bought = client.post("/events/1/quick-buy", data={"csrf_token": token})
    page = client.get(bought.location).get_data(as_text=True)
    assert "34.50 CAD" in page  # 25.00 USD x 1.38, no discount
    assert "Quantity</dt><dd>1<" in page


def test_sold_out_and_limits_show_errors_in_the_real_app(app):
    client = app.test_client()
    token = register_and_login(client, "fan@example.com")
    over = client.post("/events/6/checkout", data={"csrf_token": token, "quantity": "3", "currency": "USD"})
    assert over.status_code == 409 and "not enough tickets" in over.get_data(as_text=True)
    limit = client.post("/events/1/checkout", data={"csrf_token": token, "quantity": "5", "currency": "USD"})
    assert limit.status_code == 409 and "ticket limit" in limit.get_data(as_text=True)


def test_admin_area_end_to_end(app, seeded_database, monkeypatch, database_url):
    from app.db.commands import create_admin

    monkeypatch.setenv("EVENTHUB_ADMIN_EMAIL", "admin@eventhub.test")
    monkeypatch.setenv("EVENTHUB_ADMIN_PASSWORD", "admin-password")
    create_admin(database_url)

    buyer = app.test_client()
    buyer_token = register_and_login(buyer, "fan@example.com")
    buyer.post("/events/1/quick-buy", data={"csrf_token": buyer_token})
    assert buyer.get("/admin/audit").status_code == 403

    admin = app.test_client()
    admin.post(
        "/login",
        data={
            "csrf_token": csrf(admin, "/login"),
            "email": "admin@eventhub.test",
            "password": "admin-password",
        },
    )
    audit = admin.get("/admin/audit").get_data(as_text=True)
    assert "fan@example.com" in audit and 'data-outcome="success"' in audit

    token = csrf(admin, "/admin/rates")
    assert (
        admin.post("/admin/rates", data={"csrf_token": token, "currency": "EUR", "rate": "0.9"}).status_code
        == 302
    )
    assert "admin@eventhub.test" in admin.get("/admin/rates").get_data(as_text=True)


def test_logout_ends_the_session(app):
    client = app.test_client()
    token = register_and_login(client, "fan@example.com")
    assert client.get("/orders").status_code == 200
    client.post("/logout", data={"csrf_token": token})
    assert client.get("/orders").status_code == 302
