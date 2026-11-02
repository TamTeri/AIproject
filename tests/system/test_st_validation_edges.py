"""Black-box edge cases for purchase validation (Call 5, Thuy's list + GenAI-generated cases).

Thuy: "zero quantity, negative quantity, quantity above availability, sold-out
event, unsupported currency, purchases while logged out, all rejected with
distinct messages, all logged."

The browser itself blocks some bad values (``<input type=number min=1>``), so
to test the *server* we bypass the browser's check the way a script or an old
browser would (``tamper_quantity``). ST-12 checks the browser side separately.
"""

from __future__ import annotations

import pytest

from tests.system.support import unique_email

pytestmark = pytest.mark.system


def _reject_message(ui, event_id: str, *, quantity: str = "1", currency: str | None = None) -> str:
    ui.go(f"/events/{event_id}")
    ui.tamper_quantity(quantity)
    if currency is not None:
        ui.tamper_currency(currency)
    ui.click_button("Continue to checkout")
    return ui.error()


@pytest.mark.requirement(
    "purchase-002", "purchase-003", "purchase-008", "purchase-016", "purchase-017", "audit-001", "audit-002"
)
def test_st11_thuys_six_rejections_have_distinct_messages_and_are_all_logged(
    ui, browser_factory, db, admin_ui
):
    """ST-11 Zero, negative, too many, sold out, bad currency and logged out: six distinct messages, all audited."""
    roomy = db.create_event(capacity=3, artist="Edge Case Band")
    sold_out = db.create_event(capacity=1, artist="Sold Out Band")
    first = browser_factory()
    first.register_and_login()
    first.buy(sold_out)

    # Logged out first, in a fresh browser: the purchase must be refused and recorded.
    ui.go(f"/events/{roomy}")
    ui.click_button("Continue to checkout")
    ui.wait_for_path(r"^/login")
    logged_out = ui.flash()
    account = ui.register(email=unique_email("thuy"))
    ui.login(account.email, next_path=f"/events/{roomy}")

    messages = {
        "zero": _reject_message(ui, roomy, quantity="0"),
        "negative": _reject_message(ui, roomy, quantity="-2"),
        "too_many": _reject_message(ui, roomy, quantity="4"),
        "sold_out": _reject_message(ui, sold_out, quantity="1"),
        "currency": _reject_message(ui, roomy, quantity="1", currency="XYZ"),
        "logged_out": logged_out,
    }
    assert all(messages.values()), messages
    assert len(set(messages.values())) == 6, f"messages are not distinct: {messages}"
    assert "3" in messages["too_many"], "the message should say how many tickets are left"
    assert "sold out" in messages["sold_out"].lower()
    assert "log in" in messages["logged_out"].lower()
    assert db.hold_count(account.email) == 0 and db.order_count(account.email) == 0

    reasons = [row["reason"] for row in admin_ui.audit_rows(account.email)]
    assert len(reasons) == 5, reasons  # every logged-in rejection
    assert len(set(reasons)) == 5, f"reasons are not distinct: {reasons}"
    assert "not_authenticated" in db.audit_reasons(event_id=roomy)


@pytest.mark.requirement("purchase-001", "system-001")
def test_st12_browser_blocks_zero_before_sending_it(ui, db):
    """ST-12 Typing 0 is blocked by the browser itself; nothing reaches the server."""
    event_id = db.create_event()
    account = ui.register_and_login()
    ui.go(f"/events/{event_id}")
    ui.type("#quantity", "0")
    ui.click_button("Continue to checkout", navigates=False)
    message = ui.driver.execute_script("return document.getElementById('quantity').validationMessage")
    assert message, "the browser should explain why 0 is not allowed"
    assert ui.path == f"/events/{event_id}"
    assert db.audit_reasons(email=account.email) == []


@pytest.mark.requirement("purchase-002", "purchase-017", "system-001")
@pytest.mark.parametrize(
    "raw",
    ["1.5", "abc", "", "1e3", "0x10"],
    ids=["decimal", "letters", "blank", "exponent", "hex"],
)
def test_st13_non_whole_quantities_are_rejected_without_a_crash(ui, db, raw):
    """ST-13 GenAI edge cases: decimals, letters, blank, exponent, huge and non-ASCII digits are refused safely."""
    event_id = db.create_event()
    account = ui.register_and_login()
    message = _reject_message(ui, event_id, quantity=raw)
    assert "whole number" in message.lower(), message
    assert "Something went wrong" not in ui.page_text()
    assert db.hold_count(account.email) == 0


@pytest.mark.requirement("purchase-001", "purchase-002")
def test_st14_whole_number_written_as_2_point_0_is_accepted(ui, db):
    """ST-14 GenAI edge case: "2.0" passes the browser's check, so the server should treat it as 2."""
    event_id = db.create_event()
    ui.register_and_login()
    ui.go(f"/events/{event_id}")
    ui.type("#quantity", "2.0")
    ui.click_button("Continue to checkout")
    ui.wait_for_path(r"^/checkout/\d+$")
    assert ui.summary()["Quantity"] == "2"


@pytest.mark.requirement("inventory-001", "inventory-002", "purchase-005", "catalog-007")
def test_st15_buying_exactly_the_last_tickets_works_and_then_shows_sold_out(ui, db):
    """ST-15 Boundary: buying exactly the remaining tickets succeeds and the event then shows Sold out."""
    event_id = db.create_event(capacity=3)
    ui.register_and_login()
    ui.buy(event_id, quantity="3")
    ui.go(f"/events/{event_id}")
    assert ui.summary()["Availability"] == "Sold out"


@pytest.mark.requirement("purchase-003", "system-002")
@pytest.mark.parametrize(
    "currency", ["XYZ", "EURO", "", "e u"], ids=["unknown", "four-letters", "blank", "spaces"]
)
def test_st16_unsupported_currencies_are_rejected(ui, db, currency):
    """ST-16 Currencies outside the supported list are refused with the currency message."""
    event_id = db.create_event()
    account = ui.register_and_login()
    message = _reject_message(ui, event_id, currency=currency)
    assert "currency" in message.lower(), message
    assert db.hold_count(account.email) == 0


@pytest.mark.requirement("identity-009", "purchase-016")
def test_st17_logged_out_purchase_returns_to_the_event_after_login(ui, db):
    """ST-17 A logged-out buyer is asked to log in, then lands back on the event page with nothing bought."""
    event_id = db.create_event()
    account = ui.register()
    ui.go(f"/events/{event_id}")
    ui.click_button("Continue to checkout")
    ui.wait_for_path(r"^/login")
    assert "log in" in ui.flash().lower()
    ui.type("#email", account.email)
    ui.type("#password", account.password)
    ui.click_button("Log in")
    ui.wait_for_path(rf"^/events/{event_id}$")
    assert db.hold_count(account.email) == 0 and db.order_count(account.email) == 0


@pytest.mark.requirement("catalog-004", "system-001")
@pytest.mark.parametrize("path", ["/events/999999999", "/events/abc", "/events/-1", "/orders/999999999"])
def test_st18_unknown_ids_show_not_found_not_a_crash(ui, path):
    """ST-18 Made-up event and order ids show a friendly not-found page."""
    ui.register_and_login()
    ui.go(path)
    assert "could not find" in ui.page_text().lower()
    assert "Something went wrong" not in ui.page_text()


@pytest.mark.requirement("identity-002", "identity-005")
def test_st19_registration_rejects_short_passwords_and_duplicate_emails_in_any_case(ui):
    """ST-19 A 7-character password and an already-used email (different letter case) are refused."""
    email = unique_email("dup", "usf.edu")
    ui.register(email=email)
    ui.go("/register")
    ui.type("#name", "Again")
    ui.type("#email", email.upper())
    ui.type("#password", "password-123")
    ui.click_button("Create account")
    assert "already exists" in ui.error()

    ui.go("/register")
    ui.type("#name", "Short")
    ui.type("#email", unique_email("short"))
    ui.driver.execute_script("document.getElementById('password').removeAttribute('minlength')")
    ui.type("#password", "1234567")
    ui.click_button("Create account")
    assert "at least 8" in ui.error()


@pytest.mark.whitebox
@pytest.mark.requirement("purchase-002", "system-001")
@pytest.mark.parametrize("raw", ["²", "①", "٣"], ids=["superscript-two", "circled-one", "arabic-three"])
def test_st20_unicode_digit_quantities_are_rejected_not_crashed(ui, db, raw):
    """ST-20 White-box: str.isdigit() accepts "²", "①" and "٣" but int() cannot read all of them."""
    event_id = db.create_event()
    account = ui.register_and_login()
    message = _reject_message(ui, event_id, quantity=raw)
    assert "whole number" in message.lower(), message
    assert db.hold_count(account.email) == 0
    assert "internal_error" not in db.audit_reasons(email=account.email)


@pytest.mark.whitebox
@pytest.mark.requirement("catalog-004", "orders-002", "system-001")
@pytest.mark.parametrize("path", ["/events/²", "/orders/①", "/checkout/²"])
def test_st21_unicode_digit_ids_in_urls_show_not_found(ui, path):
    """ST-21 White-box: the same isdigit() check guards ids in URLs; they must not crash the page."""
    ui.register_and_login()
    ui.go(path)
    assert "could not find" in ui.page_text().lower(), ui.page_text()[:300]


@pytest.mark.requirement("purchase-009", "purchase-017", "system-001")
@pytest.mark.parametrize(
    "raw", ["5", "1001", "99999999999999999999"], ids=["five", "over-cap", "twenty-digits"]
)
def test_st22_very_large_whole_numbers_get_the_purchase_limit_message(ui, db, raw):
    """ST-22 A whole number above the limit (even 20 digits) gets the limit message, not a crash."""
    event_id = db.create_event()
    account = ui.register_and_login()
    message = _reject_message(ui, event_id, quantity=raw)
    assert "limit" in message.lower(), message
    assert db.hold_count(account.email) == 0


@pytest.mark.whitebox
@pytest.mark.requirement("purchase-002", "system-001")
def test_st23_a_five_thousand_digit_quantity_does_not_crash_the_server(ui, db):
    """ST-23 White-box: Python's int() refuses strings over 4,300 digits, so the server must check length first."""
    event_id = db.create_event()
    account = ui.register_and_login()
    message = _reject_message(ui, event_id, quantity="9" * 5000)
    assert "limit" in message.lower(), message
    assert "internal_error" not in db.audit_reasons(email=account.email)
