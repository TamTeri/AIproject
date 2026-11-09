"""White-box system tests: edge cases we know about because we know how the code works.

They still drive the real browser, but use the database to fast-forward time
(hold expiry, idle sessions) or to set up an exact state.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest

from tests.system.support import unique_email

pytestmark = [pytest.mark.system, pytest.mark.whitebox]


@pytest.mark.requirement("inventory-006", "purchase-012")
def test_st60_paying_after_the_hold_expired_is_refused_and_tickets_return(ui, db):
    """ST-60 The ten-minute hold runs out (fast-forwarded): Pay is refused and the tickets are released."""
    event_id = db.create_event(capacity=3)
    account = ui.register_and_login()
    ui.start_checkout(event_id, quantity="3")
    hold_id = ui.wait_for_path(r"^/checkout/\d+$").rsplit("/", 1)[-1]
    db.expire_hold(hold_id)
    ui.pay("approve")
    assert "expired" in ui.error().lower()
    assert db.order_count(account.email) == 0
    assert db.available(event_id) == 3


@pytest.mark.requirement("purchase-013", "pricing-005", "admin-003")
def test_st61_rate_change_during_checkout_does_not_change_the_price(ui, admin_ui, db):
    """ST-61 An admin changes the CAD rate while a buyer is at checkout: the buyer pays the price shown."""
    original = db.rate("CAD")
    try:
        ui.register_and_login()
        ui.start_checkout("4", quantity="2", currency="CAD")  # Comedy Collective 10.00 USD
        ui.wait_for_path(r"^/checkout/\d+$")
        shown = ui.text("dd.total")
        assert shown == "27.60 CAD"  # 20.00 x 1.38

        admin_ui.go("/admin/rates")
        row = next(r for r in admin_ui.find_all("tbody tr") if "CAD" in r.text)
        field = row.find_element("css selector", "input[name=rate]")
        field.clear()
        field.send_keys("1.50")  # +8.7%: under the 25% confirmation guard (admin-006)
        admin_ui.submit_with(row.find_element("css selector", "button"))
        assert "saved" in admin_ui.flash().lower()

        ui.pay("approve")
        ui.wait_for_path(r"^/orders/\d+")
        assert ui.text("dd.total") == shown
        ui.start_checkout("4", quantity="2", currency="CAD")
        ui.wait_for_path(r"^/checkout/\d+$")
        assert ui.text("dd.total") == "30.00 CAD"  # new buyers see the new rate (20.00 x 1.50)
    finally:
        db.set_rate("CAD", original)


@pytest.mark.requirement("identity-006", "system-008")
def test_st62_an_idle_session_expires_after_thirty_minutes(ui, db):
    """ST-62 After 31 idle minutes (fast-forwarded), the next page asks the buyer to log in again."""
    account = ui.register_and_login()
    db.idle_sessions(account.email, minutes=31)
    ui.go("/orders")
    ui.wait_for_path(r"^/login")
    assert "session expired" in ui.flash().lower()


@pytest.mark.requirement("pricing-008", "pricing-007", "pricing-003")
def test_st63_half_up_rounding_happens_once_on_the_final_amount(ui):
    """ST-63 45.00 USD -10% = 40.50 x 0.79 = 31.995 GBP, rounded half-up once to 32.00 GBP."""
    ui.register_and_login(email=unique_email("round", "usf.edu"))
    ui.start_checkout("3", quantity="1", currency="GBP")
    ui.wait_for_path(r"^/checkout/\d+$")
    assert ui.text("dd.total") == "32.00 GBP"


@pytest.mark.requirement("pricing-009", "pricing-006")
@pytest.mark.parametrize(
    ("local", "domain", "discounted"),
    [
        ("STUDENT", "USF.EDU", True),
        ("name+party", "usf.edu", False),
        ("student", "mail.usf.edu", False),
        ("student", "usf.edu.evil.com", False),
        ("student", "notusf.edu", False),
    ],
    ids=["upper-case", "plus-address", "subdomain", "lookalike-suffix", "lookalike-prefix"],
)
def test_st64_discount_eligibility_email_edge_cases(ui, db, local, domain, discounted):
    """ST-64 Kenji's Call 4 email cases end to end: only the exact usf.edu domain gets the discount."""
    event_id = db.create_event(price_minor=2000)
    ui.register_and_login(email=f"{local}-{unique_email('x').split('@')[0]}@{domain}")
    ui.start_checkout(event_id, quantity="1")
    ui.wait_for_path(r"^/checkout/\d+$")
    assert ui.text("dd.total") == ("18.00 USD" if discounted else "20.00 USD")


@pytest.mark.requirement("inventory-004", "inventory-009", "inventory-002")
def test_st65_two_browsers_racing_for_the_last_ticket(browser_factory, db):
    """ST-65 Two buyers press Continue for the last ticket at the same moment: exactly one gets it."""
    event_id = db.create_event(capacity=1)
    buyers = [browser_factory(), browser_factory()]
    for hub in buyers:
        hub.register_and_login()
        hub.go(f"/events/{event_id}")
        hub.type("#quantity", "1")
    start = threading.Barrier(len(buyers))

    def press(hub):
        start.wait()
        hub.click_button("Continue to checkout")

    threads = [threading.Thread(target=press, args=(hub,)) for hub in buyers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for hub in buyers:
        hub.wait().until(lambda _, h=hub: h.path.startswith("/checkout/") or h.exists(".error"))
    winners = [hub for hub in buyers if hub.path.startswith("/checkout/")]
    losers = [hub for hub in buyers if hub not in winners]
    assert len(winners) == 1 and len(losers) == 1
    assert "sold out" in losers[0].error().lower()
    winners[0].pay("approve")
    winners[0].wait_for_path(r"^/orders/\d+")
    assert db.available(event_id) == 0


@pytest.mark.requirement("catalog-002", "catalog-005", "catalog-006")
@pytest.mark.parametrize("query", ["%", "_", "\\", "' OR 1=1 --"])
def test_st66_search_wildcards_and_quotes_are_plain_text(ui, query):
    """ST-66 SQL wildcards and quotes in a search match nothing (they are not treated as patterns)."""
    ui.search(query)
    assert "No events matched" in ui.flash()


@pytest.mark.requirement("audit-001", "audit-003", "audit-005", "purchase-007")
def test_st67_audit_log_has_time_buyer_event_quantity_currency_and_outcome(ui, admin_ui, db):
    """ST-67 Success, rejection and payment failure all appear in the admin audit log with every field."""
    event_id = db.create_event(capacity=10, artist="Audit Trail Band")
    account = ui.register_and_login()
    ui.buy(event_id, quantity="2", currency="EUR")
    ui.start_checkout(event_id, quantity="9")
    ui.start_checkout(event_id, quantity="1", currency="GBP")
    ui.wait_for_path(r"^/checkout/\d+$")
    ui.pay("decline")

    rows = admin_ui.audit_rows(account.email)
    outcomes = sorted(r["outcome"] for r in rows)
    assert outcomes == ["failed", "rejected", "success"], rows
    success = next(r for r in rows if r["outcome"] == "success")
    assert success["event"].startswith("Audit Trail Band")
    assert (success["quantity"], success["currency"]) == ("2", "EUR")
    assert success["order"] not in ("", "—")


@pytest.mark.requirement("admin-003", "pricing-005")
def test_st68_admin_rate_form_validates_input(admin_ui, db):
    """ST-68 The admin rate form refuses zero, negative and text rates and keeps the old rate."""
    before = db.rate("GBP")
    for bad in ("0", "-1", "abc"):
        admin_ui.go("/admin/rates")
        row = next(r for r in admin_ui.find_all("tbody tr") if "GBP" in r.text)
        field = row.find_element("css selector", "input[name=rate]")
        admin_ui.driver.execute_script("arguments[0].type = 'text'", field)
        field.clear()
        field.send_keys(bad)
        admin_ui.submit_with(row.find_element("css selector", "button"))
        assert admin_ui.exists(".error"), bad
    assert db.rate("GBP") == before


@pytest.mark.requirement("purchase-018", "catalog-001")
def test_st69_event_starting_in_a_few_minutes_is_still_on_sale(ui, db):
    """ST-69 Boundary for sales closing: an event five minutes from now can still be bought."""
    event_id = db.create_event(starts_in=timedelta(minutes=5))
    ui.register_and_login()
    ui.buy(event_id)
