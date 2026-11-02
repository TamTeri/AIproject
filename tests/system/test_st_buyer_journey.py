"""Black-box system tests: the main buyer journeys, driven through a real browser.

Each expected value comes from the requirements (features/*/requirements.md)
and the seed data, not from reading the implementation (Call 5, Priya).
"""

from __future__ import annotations

import re

import pytest

from tests.system.support import unique_email

pytestmark = pytest.mark.system


@pytest.mark.requirement(
    "system-014",
    "identity-001",
    "identity-002",
    "identity-003",
    "catalog-002",
    "catalog-004",
    "pricing-003",
    "purchase-005",
    "purchase-006",
    "orders-001",
    "orders-003",
    "orders-004",
)
def test_st01_full_journey_register_search_buy_in_euros_and_find_it_in_history(ui):
    """ST-01 Register, log in, search, open an event, buy in EUR, see the confirmation, find it in history."""
    account = ui.register(name="Ana Student", email=unique_email("ana", "usf.edu"))
    ui.login(account.email)
    assert "Log out (Ana Student)" in ui.text("nav")

    ui.search("jazz")
    assert ui.card_titles() == ["Bulls Jazz Ensemble"]

    # Single click on the card body (not the link) opens the event page.
    ui.card_for("Bulls Jazz Ensemble").find_element("css selector", "p.muted").click()
    event_path = ui.wait_for_path(r"^/events/\d+$")
    assert ui.text("h1") == "Bulls Jazz Ensemble"

    event_id = event_path.rsplit("/", 1)[-1]
    ui.start_checkout(event_id, quantity="2", currency="EUR")
    ui.wait_for_path(r"^/checkout/\d+$")
    # 2 x 15.00 USD = 30.00; 10% student discount -> 27.00 USD; x 0.92 -> 24.84 EUR
    assert ui.text("dd.total") == "24.84 EUR"
    ui.pay("approve")

    confirmation = ui.wait_for_path(r"^/orders/\d+\?confirmed=1$")
    assert ui.text("h1") == "Order confirmed"
    summary = ui.summary()
    assert summary["Quantity"] == "2"
    assert summary["Currency paid"] == "EUR"
    assert "0.92" in summary["Exchange rate applied"]
    assert ui.text("dd.total") == "24.84 EUR"

    rows = ui.order_rows()
    assert len(rows) == 1 and "Bulls Jazz Ensemble" in rows[0] and "24.84 EUR" in rows[0]
    ui.find("tbody tr a").click()
    ui.wait_for_path(r"^/orders/\d+$")
    assert ui.text("dd.total") == "24.84 EUR"
    assert confirmation.split("?")[0] == ui.path


@pytest.mark.requirement("identity-007", "identity-008")
def test_st02_order_history_asks_for_login_then_returns_to_it(ui):
    """ST-02 Order history needs login and returns there after logging in."""
    ui.go("/orders")
    assert ui.wait_for_path(r"^/login\?next=/orders$")
    account = ui.register()
    ui.login(account.email, next_path="/orders")
    assert ui.wait_for_path(r"^/orders$")
    assert ui.text("h1") == "Order history"


@pytest.mark.requirement("identity-004")
def test_st03_wrong_password_gives_a_generic_error(ui):
    """ST-03 A wrong password and an unknown email give the same generic error."""
    account = ui.register()
    ui.login(account.email, "wrong-password-1")
    wrong_password = ui.error()
    ui.login(unique_email("nobody"), "wrong-password-1")
    assert ui.error() == wrong_password == "Invalid email or password."


@pytest.mark.requirement("catalog-001", "catalog-003", "catalog-005", "catalog-007")
def test_st04_search_by_venue_and_no_match_shows_everything(ui):
    """ST-04 Venue search matches; an unmatched search says so and lists every event."""
    ui.search("USF Arena")
    assert sorted(ui.card_titles()) == ["EventHub Demo", "The Sun Dogs"]
    ui.search("polka")
    assert "No events matched" in ui.flash()
    assert len(ui.card_titles()) >= 6
    ui.card_for("Tampa Symphony").find_element("css selector", "h2 a").click()
    ui.wait_for_path(r"^/events/\d+$")
    assert re.search(r"\d+ tickets left", ui.summary()["Availability"])


@pytest.mark.requirement("catalog-008", "catalog-011", "purchase-011")
def test_st05_double_click_on_a_card_quick_buys_one_ticket(ui, db):
    """ST-05 Double-clicking an event card buys exactly one ticket in the saved currency."""
    account = ui.register_and_login()
    ui.go("/events")
    ui.double_click(ui.card_for("Comedy Collective").find_element("css selector", "p.muted"))
    ui.wait_for_path(r"^/orders/\d+\?confirmed=1$")
    assert ui.summary()["Quantity"] == "1"
    assert ui.text("dd.total") == "10.00 USD"  # 10.00 USD, no student discount for example.com
    assert db.order_count(account.email) == 1


@pytest.mark.requirement("purchase-004", "purchase-012", "inventory-008")
def test_st06_declined_card_releases_tickets_and_creates_no_order(ui, db):
    """ST-06 A declined simulated card creates no order and gives the tickets back."""
    event_id = db.create_event(capacity=5)
    account = ui.register_and_login()
    ui.start_checkout(event_id, quantity="3")
    ui.wait_for_path(r"^/checkout/\d+$")
    assert db.available(event_id) == 2  # held while checking out
    ui.pay("decline")
    assert "declined" in ui.error()
    assert db.order_count(account.email) == 0
    ui.go(f"/events/{event_id}")
    assert ui.summary()["Availability"] == "5 tickets left"


@pytest.mark.requirement("inventory-005", "inventory-008")
def test_st07_cancel_gives_held_tickets_back(ui, db):
    """ST-07 Cancelling checkout releases the held tickets immediately."""
    event_id = db.create_event(capacity=4)
    ui.register_and_login()
    ui.start_checkout(event_id, quantity="4")
    ui.wait_for_path(r"^/checkout/\d+$")
    assert "held for 10 minutes" in ui.flash()
    ui.click_button("Cancel and release tickets")
    assert "released" in ui.flash()
    ui.go(f"/events/{event_id}")
    assert ui.summary()["Availability"] == "4 tickets left"


@pytest.mark.requirement("identity-013", "identity-007")
def test_st08_logout_ends_the_session(ui):
    """ST-08 After logging out, protected pages need login again."""
    ui.register_and_login()
    ui.logout()
    assert "You have been logged out." in ui.flash()
    ui.go("/orders")
    assert ui.wait_for_path(r"^/login")


@pytest.mark.requirement("catalog-009", "catalog-010", "catalog-011")
@pytest.mark.parametrize("path", ["/events", "/events/1", "/login", "/register"])
def test_st09_phone_width_pages_do_not_scroll_sideways(browser_factory, path):
    """ST-09 At phone width (375 px) no page scrolls sideways, and Quick Buy is a button."""
    phone = browser_factory(width=375, height=800, mobile=True)
    phone.go(path)
    phone.find("h1")
    overflow = phone.driver.execute_script("return document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 0, f"{path} scrolls sideways by {overflow}px"
    if path == "/events/1":
        assert any(b.text == "Quick Buy" or b.text.startswith("Quick Buy") for b in phone.find_all("button"))


@pytest.mark.requirement("purchase-009")
def test_st10_purchase_limit_of_four_per_account_per_event(ui, db):
    """ST-10 Five tickets are refused; three then two are refused; three then one is fine."""
    event_id = db.create_event(capacity=50)
    account = ui.register_and_login()
    ui.start_checkout(event_id, quantity="5")
    assert "limit" in ui.error()
    ui.buy(event_id, quantity="3")
    ui.start_checkout(event_id, quantity="2")
    assert "limit" in ui.error()
    ui.buy(event_id, quantity="1")
    assert db.order_count(account.email, event_id) == 2
