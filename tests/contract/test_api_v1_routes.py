"""Web boundary contract tests: routes + templates with fake services.

No database. Checks login redirects, ownership, admin-only pages, CSRF,
escaping, and that purchase outcomes become the right pages/status codes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from app.identity.contracts import Principal
from app.web import create_web_app
from app.web.services import ServiceError

BUYER = Principal("buyer-1", "Buyer", "buyer@usf.edu", preferred_currency="EUR")
ADMIN = Principal("admin-1", "Admin", "admin@eventhub.test", role="administrator")
EVENT = {
    "id": "event-1",
    "title": "Demo Night",
    "artist": "A & B",
    "venue": "Main Hall",
    "starts_at": "2026-11-01T20:00:00Z",
    "available": 12,
    "base_price_minor": 2500,
}


@dataclass
class CatalogFake:
    events: list[dict]

    def list_events(self, *, query: str | None = None):
        matches = [e for e in self.events if query and query.lower() in e["artist"].lower()]
        if not query:
            return {"events": self.events, "query": None, "no_match": False}
        return {"events": matches or self.events, "query": query, "no_match": not matches}

    def get_event(self, *, event_id: str):
        return next((event for event in self.events if event["id"] == event_id), None)


class IdentityFake:
    def __init__(self) -> None:
        self.tokens = {"buyer-token": BUYER, "admin-token": ADMIN}
        self.ended: list[str] = []

    def register(self, **kwargs):
        if "@" not in kwargs["email"]:
            raise ServiceError("invalid-registration", "Email must be a valid address.", 400)
        return {"account_id": "new", "name": kwargs["name"], "email": kwargs["email"]}

    def authenticate(self, *, email, password):
        if password != "right-password":
            raise ServiceError("invalid-credentials", "Invalid email or password.", 401)
        return ADMIN if email.startswith("admin") else BUYER

    def start_session(self, *, account_id):
        return "admin-token" if account_id == "admin-1" else "buyer-token"

    def resolve_session(self, *, token):
        return self.tokens.get(token)

    def end_session(self, *, token):
        self.ended.append(token)

    def set_preferred_currency(self, *, account_id, currency):
        if currency not in {"USD", "EUR"}:
            raise ServiceError("unsupported-currency", "That currency is not supported.", 400)


class PricingFake:
    def currencies(self):
        return ["EUR", "USD"]

    def base_price_display(self, *, base_price_minor):
        return f"{base_price_minor / 100:.2f} USD"


@dataclass
class CheckoutFake:
    start_outcome: str = "hold_created"
    pay_outcome: str = "success"
    calls: list[tuple] = field(default_factory=list)

    def start(self, **kwargs):
        self.calls.append(("start", kwargs))
        return SimpleNamespace(outcome=self.start_outcome, hold=SimpleNamespace(id="hold-1"))

    def review(self, *, buyer_id, hold_id):
        if hold_id != "hold-1" or buyer_id != "buyer-1":
            return None
        return SimpleNamespace(
            hold_id="hold-1",
            event_id="event-1",
            event_title="Demo Night",
            quantity=2,
            currency="EUR",
            subtotal="46.00 EUR",
            discount="4.60 EUR",
            discount_applied=True,
            total="41.40 EUR",
            exchange_rate="0.92",
            expires_at="2026-11-01 12:10",
            status="active",
        )

    def pay(self, **kwargs):
        self.calls.append(("pay", kwargs))
        return SimpleNamespace(outcome=self.pay_outcome, order=SimpleNamespace(id="order-9"))

    def cancel(self, **kwargs):
        self.calls.append(("cancel", kwargs))
        return SimpleNamespace(outcome="cancelled")

    def quick_buy(self, **kwargs):
        self.calls.append(("quick_buy", kwargs))
        return SimpleNamespace(outcome=self.pay_outcome, order=SimpleNamespace(id="order-9"))


class OrdersFake:
    def list_for_buyer(self, *, buyer_id):
        return [
            SimpleNamespace(id="order-9", artist="A & B", quantity=2, total="41.40 EUR", created_at="today")
        ]

    def get_for_buyer(self, *, buyer_id, order_id):
        if order_id != "order-9" or buyer_id != "buyer-1":
            return None
        return SimpleNamespace(
            id="order-9",
            event_title="Demo Night",
            artist="A & B",
            venue="Main Hall",
            starts_at="soon",
            quantity=2,
            currency="EUR",
            exchange_rate="0.92",
            subtotal="46.00 EUR",
            discount="4.60 EUR",
            discount_applied=True,
            total="41.40 EUR",
            created_at="today",
        )


class AdminFake:
    def __init__(self) -> None:
        self.saved: list[tuple] = []

    def list_rates(self, *, actor):
        from decimal import Decimal

        return [
            SimpleNamespace(currency="USD", rate=Decimal("1"), updated_at=None, updated_by=None),
            SimpleNamespace(currency="EUR", rate=Decimal("0.92"), updated_at=None, updated_by=None),
        ]

    def set_rate(self, *, actor, currency, rate):
        if rate.startswith("-"):
            raise ServiceError("invalid-rate", "Rate must be greater than 0.", 400)
        self.saved.append((actor.account_id, currency, rate))

    def audit_page(self, *, actor, before_id=None):
        rows = [
            SimpleNamespace(
                id="1",
                submitted_at="now",
                buyer_email="b@usf.edu",
                event_title="Demo",
                quantity=1,
                currency="USD",
                outcome="success",
                reason_code="success",
                order_id="9",
            )
        ]
        return SimpleNamespace(rows=rows, next_before_id=None)


@dataclass
class ServicesFake:
    catalog: CatalogFake
    identity: IdentityFake = field(default_factory=IdentityFake)
    pricing: PricingFake = field(default_factory=PricingFake)
    checkout: CheckoutFake = field(default_factory=CheckoutFake)
    orders: OrdersFake = field(default_factory=OrdersFake)
    admin: AdminFake = field(default_factory=AdminFake)

    @property
    def purchase(self):
        return self.checkout


@pytest.fixture
def services():
    return ServicesFake(catalog=CatalogFake(events=[dict(EVENT)]))


@pytest.fixture
def client(services):
    app = create_web_app(services=services, config={"TESTING": True, "SECRET_KEY": "test"})
    return app.test_client()


def login_as(client, token: str = "buyer-token") -> str:
    with client.session_transaction() as session:
        session["session_token"] = token
        session["csrf_token"] = "csrf-test"
    return "csrf-test"


# --------------------------------------------------------------- catalog


def test_catalog_search_escapes_query_and_event_detail_has_one_explicit_quick_buy_button(client):
    search = client.get("/events?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E")
    assert search.status_code == 200
    body = search.get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<script>alert(1)</script>" not in body

    detail = client.get("/events/event-1")
    assert detail.status_code == 200
    detail_body = detail.get_data(as_text=True)
    assert detail_body.count(">Quick Buy<") == 1
    assert "ondblclick" not in detail_body
    assert "12</strong> tickets left" in detail_body  # catalog-007 availability
    assert "25.00 USD per ticket" in detail_body


def test_no_match_message_then_full_list(client):
    body = client.get("/events?q=polka").get_data(as_text=True)
    assert "No events matched “polka”. Showing all events." in body
    assert "A &amp; B" in body


def test_event_cards_support_single_and_double_click_without_inline_handlers(client):
    body = client.get("/events").get_data(as_text=True)
    assert 'data-event-url="/events/event-1"' in body
    assert 'class="quick-buy-form"' in body and 'action="/events/event-1/quick-buy"' in body
    assert "ondblclick" not in body and "onclick" not in body
    script = client.get("/assets/eventhub.js")
    assert script.status_code == 200
    js = script.get_data(as_text=True)
    assert "dblclick" in js and "click" in js


def test_unknown_event_is_404(client):
    assert client.get("/events/nope").status_code == 404


def test_pages_are_responsive_and_send_security_headers(client):
    response = client.get("/events")
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in response.get_data(as_text=True)
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


# -------------------------------------------------------------- identity


def test_login_sets_session_and_returns_to_requested_page(client):
    page = client.get("/login?next=/orders").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    response = client.post(
        "/login",
        data={"csrf_token": token, "email": "b@usf.edu", "password": "right-password", "next": "/orders"},
    )
    assert response.status_code == 302
    assert response.location == "/orders"
    with client.session_transaction() as session:
        assert session["session_token"] == "buyer-token"


@pytest.mark.parametrize(
    "target", ["https://evil.example/", "//evil.example", "/\\evil", "javascript:alert(1)"]
)
def test_login_never_redirects_off_site(client, target):
    login_as(client, token="none")
    response = client.post(
        "/login",
        data={"csrf_token": "csrf-test", "email": "b@usf.edu", "password": "right-password", "next": target},
    )
    assert response.location == "/events"


def test_wrong_password_shows_generic_error(client):
    login_as(client, token="none")
    response = client.post(
        "/login", data={"csrf_token": "csrf-test", "email": "b@usf.edu", "password": "nope"}
    )
    assert response.status_code == 401
    assert "Invalid email or password." in response.get_data(as_text=True)


def test_register_errors_are_shown_and_fields_kept(client):
    login_as(client, token="none")
    response = client.post(
        "/register", data={"csrf_token": "csrf-test", "name": "Ada", "email": "bad", "password": "x"}
    )
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "Email must be a valid address." in body and 'value="Ada"' in body


def test_logout_ends_server_session(client, services):
    token = login_as(client)
    response = client.post("/logout", data={"csrf_token": token})
    assert response.status_code == 302
    assert services.identity.ended == ["buyer-token"]


def test_expired_session_is_dropped_and_login_says_so(client):
    login_as(client, token="expired-token")
    response = client.get("/orders")
    assert response.status_code == 302 and response.location.startswith("/login")
    assert "Your session expired" in client.get(response.location).get_data(as_text=True)


# ------------------------------------------------- protected pages (identity-007..010)


@pytest.mark.parametrize("path", ["/orders", "/orders/order-9", "/checkout/hold-1", "/account"])
def test_protected_pages_redirect_to_login_and_show_nothing(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert response.location == f"/login?next={path}"
    assert "41.40" not in response.get_data(as_text=True)


def test_unauthenticated_checkout_post_creates_nothing(client, services):
    login_as(client, token="none")
    response = client.post(
        "/events/event-1/checkout", data={"csrf_token": "csrf-test", "quantity": "1", "currency": "USD"}
    )
    assert response.status_code == 302
    assert response.location == "/login?next=/events/event-1"
    assert services.checkout.calls == []


def test_other_buyers_order_is_not_found(client):
    login_as(client)
    assert client.get("/orders/order-10").status_code == 404


# -------------------------------------------------------------- purchase


def test_checkout_review_pay_and_confirmation(client, services):
    token = login_as(client)
    start = client.post(
        "/events/event-1/checkout", data={"csrf_token": token, "quantity": "2", "currency": "EUR"}
    )
    assert start.location == "/checkout/hold-1"
    assert services.checkout.calls[0][1] == {
        "buyer_id": "buyer-1",
        "event_id": "event-1",
        "quantity": "2",
        "currency": "EUR",
    }

    review = client.get("/checkout/hold-1").get_data(as_text=True)
    assert "41.40 EUR" in review and "4.60 EUR" in review

    paid = client.post("/checkout/hold-1/pay", data={"csrf_token": token, "payment": "approve"})
    assert paid.location == "/orders/order-9?confirmed=1"
    confirmation = client.get(paid.location).get_data(as_text=True)
    assert "Order confirmed" in confirmation
    assert "no email" in confirmation  # system-006: on-screen confirmation only
    for text in ("Demo Night", "EUR", "0.92", "41.40 EUR"):
        assert text in confirmation  # orders-003


@pytest.mark.parametrize(
    ("outcome", "status", "message"),
    [
        ("invalid_quantity", 400, "whole number"),
        ("unsupported_currency", 400, "currency is not supported"),
        ("sold_out", 409, "not enough tickets"),
        ("limit_exceeded", 409, "ticket limit"),
    ],
)
def test_checkout_rejections_show_specific_messages(client, services, outcome, status, message):
    services.checkout.start_outcome = outcome
    token = login_as(client)
    response = client.post(
        "/events/event-1/checkout", data={"csrf_token": token, "quantity": "2", "currency": "EUR"}
    )
    assert response.status_code == status
    body = response.get_data(as_text=True)
    assert message in body
    assert f'data-error-code="{outcome}"' in body


def test_declined_payment_explains_no_order(client, services):
    services.checkout.pay_outcome = "payment_failed"
    token = login_as(client)
    response = client.post("/checkout/hold-1/pay", data={"csrf_token": token, "payment": "decline"})
    assert response.status_code == 402
    assert "no order was created" in response.get_data(as_text=True)


def test_quick_buy_uses_saved_currency_and_standard_path(client, services):
    token = login_as(client)
    response = client.post("/events/event-1/quick-buy", data={"csrf_token": token})
    assert response.location == "/orders/order-9?confirmed=1"
    assert services.checkout.calls == [
        ("quick_buy", {"buyer_id": "buyer-1", "event_id": "event-1", "currency": "EUR"})
    ]


def test_cancel_releases_and_returns_to_events(client, services):
    token = login_as(client)
    response = client.post("/checkout/hold-1/cancel", data={"csrf_token": token})
    assert response.location == "/events"


# ------------------------------------------------------------------ CSRF


@pytest.mark.parametrize(
    "path",
    [
        "/events/event-1/checkout",
        "/events/event-1/quick-buy",
        "/checkout/hold-1/pay",
        "/logout",
        "/admin/rates",
    ],
)
def test_posts_without_csrf_token_are_rejected(client, services, path):
    login_as(client)
    response = client.post(path, data={"quantity": "1", "currency": "USD"})
    assert response.status_code == 400
    assert services.checkout.calls == []


# ----------------------------------------------------------------- admin


@pytest.mark.parametrize("path", ["/admin", "/admin/rates", "/admin/audit"])
def test_buyers_cannot_open_admin_pages(client, path):
    login_as(client)
    assert client.get(path).status_code == 403


def test_anonymous_admin_access_redirects_to_login(client):
    assert client.get("/admin/audit").status_code == 302


def test_admin_sees_rates_and_audit_and_can_update(client, services):
    token = login_as(client, "admin-token")
    rates = client.get("/admin/rates").get_data(as_text=True)
    assert "EUR" in rates and "0.92" in rates
    audit = client.get("/admin/audit").get_data(as_text=True)
    assert "b@usf.edu" in audit and 'data-outcome="success"' in audit

    saved = client.post("/admin/rates", data={"csrf_token": token, "currency": "EUR", "rate": "0.95"})
    assert saved.status_code == 302
    assert services.admin.saved == [("admin-1", "EUR", "0.95")]

    bad = client.post("/admin/rates", data={"csrf_token": token, "currency": "EUR", "rate": "-1"})
    assert bad.status_code == 400
    assert "greater than 0" in bad.get_data(as_text=True)


def test_admin_link_only_shown_to_admins(client):
    login_as(client)
    assert ">Admin<" not in client.get("/events").get_data(as_text=True)
    login_as(client, "admin-token")
    assert ">Admin<" in client.get("/events").get_data(as_text=True)


def test_saved_currency_setting(client):
    token = login_as(client)
    assert client.post("/account", data={"csrf_token": token, "currency": "USD"}).status_code == 302
    assert client.post("/account", data={"csrf_token": token, "currency": "XYZ"}).status_code == 400
