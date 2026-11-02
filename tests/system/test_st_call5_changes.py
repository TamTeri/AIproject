"""System tests for the behaviour Call 5 asked for (requirement gaps and findings).

- purchase-014: the buy button firing twice must not create two orders (Thuy, Priya).
- purchase-015: request speed is limited per account (Kenji, finding 2).
- pricing-011 / identity-014: the discount follows the *current* email (Kenji, finding 1).
- orders-006: one clearly labelled amount charged (Darnell's "sketchy" confirmation page).
- catalog-012 / identity-015: where the preselected currency comes from (Darnell).
- purchase-018: no ticket sales once the event has started (found while writing these tests).
"""

from __future__ import annotations

import re
from datetime import timedelta

import pytest

from tests.system.support import unique_email

pytestmark = pytest.mark.system

# Submit the given form twice at the same moment, exactly as a double-fired
# button or a retrying script would, and report where each request ended up.
DOUBLE_SUBMIT_JS = """
const form = document.querySelector(arguments[0]);
const done = arguments[arguments.length - 1];
const send = () => fetch(form.action, {method: 'POST', body: new FormData(form), credentials: 'same-origin'})
    .then(r => ({status: r.status, url: new URL(r.url).pathname}));
Promise.all([send(), send()]).then(done, e => done(String(e)));
"""


# ------------------------------------------------------- purchase-014 double purchase


@pytest.mark.requirement("purchase-014", "audit-008")
def test_st30_pay_submitted_twice_at_once_creates_one_order(ui, db, admin_ui):
    """ST-30 Two simultaneous Pay submissions: one order, and both land on the same confirmation."""
    event_id = db.create_event(capacity=10)
    account = ui.register_and_login()
    ui.start_checkout(event_id, quantity="2")
    ui.wait_for_path(r"^/checkout/\d+$")
    results = ui.driver.execute_async_script(DOUBLE_SUBMIT_JS, "form[action$='/pay']")
    assert isinstance(results, list), results
    assert db.order_count(account.email, event_id) == 1
    assert [r["status"] for r in results] == [200, 200], results
    assert results[0]["url"] == results[1]["url"] and results[0]["url"].startswith("/orders/"), results
    reasons = [r["reason"] for r in admin_ui.audit_rows(account.email)]
    assert sorted(reasons) == ["replayed", "success"], reasons


@pytest.mark.requirement("purchase-014", "catalog-008")
def test_st31_quick_buy_submitted_twice_at_once_creates_one_order(ui, db):
    """ST-31 Two simultaneous Quick Buy submissions buy one ticket, not two."""
    event_id = db.create_event(capacity=10)
    account = ui.register_and_login()
    ui.go(f"/events/{event_id}")
    results = ui.driver.execute_async_script(DOUBLE_SUBMIT_JS, "form[action$='/quick-buy']")
    assert isinstance(results, list), results
    assert db.order_count(account.email, event_id) == 1, results
    assert results[0]["url"] == results[1]["url"], results


@pytest.mark.requirement("purchase-014", "purchase-006")
def test_st32_impatient_double_click_on_pay_shows_the_confirmation(ui, db):
    """ST-32 Double-clicking Pay (impatient thumb) ends on the order confirmation with one order."""
    event_id = db.create_event(capacity=10)
    account = ui.register_and_login()
    ui.start_checkout(event_id, quantity="1")
    ui.wait_for_path(r"^/checkout/\d+$")
    pay = ui.find("form[action$='/pay'] button[type=submit]")
    ui.double_click(pay)
    ui.wait_for_path(r"^/orders/\d+")
    assert ui.text("h1") == "Order confirmed"
    assert db.order_count(account.email, event_id) == 1


@pytest.mark.requirement("purchase-014", "catalog-008")
def test_st33_double_clicking_the_quick_buy_button_buys_one_ticket(ui, db):
    """ST-33 Double-clicking the Quick Buy button (not the card) buys one ticket."""
    event_id = db.create_event(capacity=10)
    account = ui.register_and_login()
    ui.go(f"/events/{event_id}")
    ui.double_click(ui.find("form[action$='/quick-buy'] button"))
    ui.wait_for_path(r"^/orders/\d+")
    assert db.order_count(account.email, event_id) == 1


@pytest.mark.requirement("purchase-014", "purchase-005")
def test_st34_buying_again_on_purpose_still_works(ui, db):
    """ST-34 The duplicate guard must not block a deliberate second purchase from a freshly opened page."""
    event_id = db.create_event(capacity=10)
    account = ui.register_and_login()
    ui.buy(event_id, quantity="1")
    ui.buy(event_id, quantity="1")
    assert db.order_count(account.email, event_id) == 2


@pytest.mark.requirement("purchase-014", "purchase-006")
def test_st35_refreshing_the_confirmation_does_not_buy_again(ui, db):
    """ST-35 Reloading the confirmation page or pressing Back does not create another order."""
    event_id = db.create_event(capacity=10)
    account = ui.register_and_login()
    ui.buy(event_id, quantity="1")
    ui.driver.refresh()
    ui.find("h1")
    ui.driver.back()
    ui.find("h1")
    assert db.order_count(account.email, event_id) == 1


# ------------------------------------------------------------ purchase-015 rate limit


@pytest.mark.requirement("purchase-015", "audit-008")
def test_st36_more_than_ten_purchase_requests_a_minute_are_slowed_down(ui, db):
    """ST-36 The 11th purchase request inside a minute is refused with a wait message and audited."""
    event_id = db.create_event(capacity=10)
    account = ui.register_and_login()
    for _ in range(10):
        ui.go(f"/events/{event_id}")
        ui.tamper_quantity("0")
        ui.click_button("Continue to checkout")
        assert "Too many" not in ui.page_text()
    ui.go(f"/events/{event_id}")
    ui.click_button("Continue to checkout")  # a valid request, but over the limit
    assert "too many" in ui.error().lower()
    assert "minute" in ui.error().lower()
    assert db.hold_count(account.email) == 0
    assert db.audit_reasons(email=account.email)[-1] == "rate_limited"


@pytest.mark.requirement("purchase-015")
def test_st37_one_buyers_limit_does_not_slow_down_another_buyer(ui, browser_factory, db):
    """ST-37 The limit is per account: a hammering account does not block a normal buyer."""
    event_id = db.create_event(capacity=10)
    ui.register_and_login()
    for _ in range(11):
        ui.go(f"/events/{event_id}")
        ui.tamper_quantity("0")
        ui.click_button("Continue to checkout")
    other = browser_factory()
    other_account = other.register_and_login()
    other.buy(event_id)
    assert db.order_count(other_account.email, event_id) == 1


# ------------------------------------------------ pricing-011 discount follows the email


def _change_email(ui, new_email: str, password: str) -> None:
    ui.go("/account")
    ui.type("#new-email", new_email)
    ui.type("#current-password", password)
    ui.click_button("Change email")


@pytest.mark.requirement("pricing-011", "identity-014", "pricing-009")
def test_st38_changing_to_a_non_usf_email_removes_the_discount(ui, db):
    """ST-38 Kenji's finding: register with @usf.edu, switch to gmail, the discount must go away."""
    account = ui.register_and_login(email=unique_email("kenji", "usf.edu"))
    event_id = db.create_event(price_minor=2000)
    ui.start_checkout(event_id, quantity="1")
    ui.wait_for_path(r"^/checkout/\d+$")
    assert ui.text("dd.total") == "18.00 USD"  # 20.00 - 10%
    ui.click_button("Cancel and release tickets")

    _change_email(ui, unique_email("kenji", "gmail.com"), account.password)
    assert "saved" in ui.flash().lower() or "changed" in ui.flash().lower()
    ui.start_checkout(event_id, quantity="1")
    ui.wait_for_path(r"^/checkout/\d+$")
    assert ui.text("dd.total") == "20.00 USD"
    assert "discount" not in ui.text("dl.summary").lower()


@pytest.mark.requirement("pricing-011", "purchase-013")
def test_st39_email_change_during_checkout_cancels_the_discounted_hold(ui, browser_factory, db):
    """ST-39 A hold priced with the discount cannot be paid after the email stops qualifying."""
    account = ui.register_and_login(email=unique_email("swap", "usf.edu"))
    buyer_id = db.account_id(account.email)
    event_id = db.create_event(capacity=5, price_minor=2000)
    ui.start_checkout(event_id, quantity="2")
    checkout = ui.wait_for_path(r"^/checkout/\d+$")

    other_tab = browser_factory()
    other_tab.login(account.email, account.password)
    _change_email(other_tab, unique_email("swap", "gmail.com"), account.password)

    ui.go(checkout)
    ui.pay("approve")
    message = ui.error().lower()
    assert "discount" in message and "start again" in message, message
    orders = db.scalar(
        "SELECT COUNT(*) FROM orders WHERE buyer_id = :b AND event_id = :e", b=int(buyer_id), e=int(event_id)
    )
    assert orders == 0
    assert db.available(event_id) == 5


@pytest.mark.requirement("identity-014")
def test_st40_email_change_needs_the_password_and_a_free_address(ui, browser_factory):
    """ST-40 Changing the email needs the current password and cannot take another account's email."""
    taken = browser_factory().register(email=unique_email("taken"))
    account = ui.register_and_login()
    _change_email(ui, unique_email("new"), "not-my-password")
    assert "password" in ui.error().lower()
    _change_email(ui, taken.email, account.password)
    assert "already" in ui.error().lower()
    ui.go("/account")
    assert account.email in ui.text("dl.summary")


# ------------------------------------------------- orders-006 confirmation wording


@pytest.mark.requirement("orders-006", "orders-003", "pricing-003")
def test_st41_checkout_and_confirmation_show_one_clear_amount_charged(ui, db):
    """ST-41 Darnell's finding: one labelled amount charged in the paid currency; USD price marked reference."""
    ui.register_and_login(email=unique_email("darnell"))
    ui.start_checkout("3", quantity="1", currency="EUR")  # Tampa Symphony, 45.00 USD
    ui.wait_for_path(r"^/checkout/\d+$")
    for page in ("checkout", "confirmation"):
        charged = ui.find("#amount-charged")
        assert charged.text.strip() == "41.40 EUR", page  # 45.00 x 0.92, no discount
        label = ui.find("#amount-charged-label").text.lower()
        assert "charged" in label and "card" in label, (page, label)
        reference = ui.find("#usd-reference").text.lower()
        assert "45.00 usd" in reference and "not charged" in reference, (page, reference)
        assert "0.92" in ui.page_text()
        if page == "checkout":
            ui.pay("approve")
            ui.wait_for_path(r"^/orders/\d+")


# ------------------------------------------- catalog-012 / identity-015 home currency


@pytest.mark.requirement("catalog-012", "identity-015")
def test_st42_preselected_currency_says_where_it_comes_from(ui):
    """ST-42 The event page and Quick Buy say which currency is used and that it is the saved home currency."""
    ui.go("/register")
    ui.type("#name", "Intl Student")
    email = unique_email("intl")
    ui.type("#email", email)
    ui.type("#password", "password-123")
    help_text = ui.text("#home-currency-help").lower()
    assert "checkout" in help_text and "quick buy" in help_text
    ui.choose("#home-currency", "GBP")
    ui.click_button("Create account")
    ui.login(email)

    ui.go("/events/1")
    assert ui.selected("#currency") == "GBP"
    note = ui.find("#currency-source")
    assert "GBP" in note.text and "saved" in note.text.lower()
    assert note.find_element("css selector", "a").get_attribute("href").endswith("/account")
    assert "GBP" in ui.find("form[action$='/quick-buy'] button").text


@pytest.mark.requirement("catalog-012")
def test_st43_changing_the_saved_currency_changes_the_preselection(ui):
    """ST-43 After saving CAD on the Account page, the event page preselects CAD and says so."""
    ui.register_and_login()
    ui.go("/account")
    ui.choose("#currency", "CAD")
    ui.click_button("Save")
    ui.go("/events/2")
    assert ui.selected("#currency") == "CAD"
    assert "CAD" in ui.text("#currency-source")


# -------------------------------------------------------- purchase-018 sales closed


@pytest.mark.requirement("purchase-018", "audit-008")
def test_st44_no_tickets_are_sold_after_the_event_has_started(ui, db):
    """ST-44 An event that started yesterday shows that sales have closed and refuses a forced purchase."""
    event_id = db.create_event(starts_in=-timedelta(days=1), artist="Yesterday's Band")
    account = ui.register_and_login()
    ui.go(f"/events/{event_id}")
    assert "sales have closed" in ui.page_text().lower()
    assert not ui.exists("form[action$='/checkout']")
    # Force a Quick Buy POST anyway, with a valid form token, as a script would.
    status = ui.driver.execute_async_script(
        """
        const done = arguments[arguments.length - 1];
        const body = new FormData();
        body.append('csrf_token', document.querySelector('input[name=csrf_token]').value);
        body.append('idempotency_key', 'forced-by-a-script-' + Date.now());
        fetch(arguments[0], {method: 'POST', body, credentials: 'same-origin'})
            .then(r => r.text().then(t => done([r.status, t])));
        """,
        f"/events/{event_id}/quick-buy",
    )
    assert re.search("sales have closed", status[1], re.I), status[0]
    assert db.order_count(account.email, event_id) == 0
    assert "sales_closed" in db.audit_reasons(email=account.email)
