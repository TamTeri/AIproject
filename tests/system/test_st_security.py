"""Black-box security checks through the browser (Kenji's "basics", re-run every build)."""

from __future__ import annotations

import pytest

from tests.system.support import PASSWORD, unique_email

pytestmark = pytest.mark.system


@pytest.mark.requirement("catalog-006")
def test_st50_search_text_is_shown_as_text_never_as_markup(ui):
    """ST-50 A search containing HTML and a script is displayed literally and never runs."""
    attack = '<b id="injected">bold</b><img src=x onerror="window.__xss=1">'
    ui.search(attack)
    assert not ui.exists("#injected")
    assert ui.driver.execute_script("return window.__xss === undefined")
    assert attack in ui.flash()


@pytest.mark.requirement("identity-001", "catalog-006")
def test_st51_names_with_markup_or_accents_are_shown_as_typed(ui):
    """ST-51 A name with markup and non-English letters is stored and shown exactly as typed."""
    name = 'José Ñúñez 李 <i id="nm">x</i>'
    ui.register_and_login(name=name)
    assert f"Log out ({name})" in ui.text("nav")
    assert not ui.exists("#nm")


@pytest.mark.requirement("identity-008")
@pytest.mark.parametrize("target", ["https://evil.example/", "//evil.example/", "/\\evil.example"])
def test_st52_login_never_redirects_to_another_site(ui, target):
    """ST-52 A crafted ?next= pointing at another site is ignored after login."""
    account = ui.register()
    ui.login(account.email, next_path=target)
    assert ui.driver.current_url.startswith(ui.base_url), ui.driver.current_url
    assert ui.path.startswith("/events")


@pytest.mark.requirement("identity-010", "orders-001")
def test_st53_a_buyer_cannot_open_another_buyers_order_or_checkout(ui, browser_factory, db):
    """ST-53 Order and checkout URLs from one buyer show not-found to another buyer."""
    event_id = db.create_event(capacity=10)
    ui.register_and_login()
    order_path = ui.buy(event_id).split("?")[0]
    ui.start_checkout(event_id, quantity="1")
    checkout_path = ui.wait_for_path(r"^/checkout/\d+$")

    other = browser_factory()
    other.register_and_login()
    for path in (order_path, checkout_path):
        other.go(path)
        assert "could not find" in other.page_text().lower(), path


@pytest.mark.requirement("admin-002", "identity-011", "audit-006")
@pytest.mark.parametrize("path", ["/admin", "/admin/rates", "/admin/audit"])
def test_st54_buyers_cannot_reach_the_admin_area(ui, path):
    """ST-54 A logged-in buyer sees "Administrators only." on every admin page."""
    ui.register_and_login()
    ui.go(path)
    assert "Administrators only." in ui.page_text()
    assert "Admin" not in [a.text for a in ui.find_all("nav a")]


@pytest.mark.requirement("system-001")
def test_st55_a_form_with_a_forged_token_is_refused(ui, db):
    """ST-55 A purchase form whose CSRF token was changed is refused and buys nothing."""
    event_id = db.create_event(capacity=10)
    account = ui.register_and_login()
    ui.go(f"/events/{event_id}")
    ui.driver.execute_script(
        "document.querySelector(\"form[action$='/checkout'] input[name=csrf_token]\").value = 'forged'"
    )
    ui.click_button("Continue to checkout")
    assert "form expired" in ui.page_text().lower()
    assert db.hold_count(account.email) == 0


@pytest.mark.whitebox
@pytest.mark.requirement("identity-005")
def test_st56_passwords_are_stored_only_as_hashes(ui, db):
    """ST-56 White-box: the database holds a PBKDF2 hash, never the password."""
    account = ui.register(email=unique_email("hash"))
    stored = db.scalar("SELECT password_hash FROM accounts WHERE normalized_email = :e", e=account.email)
    assert stored.startswith("pbkdf2_sha256$") and PASSWORD not in stored


@pytest.mark.requirement("identity-003", "pricing-009")
def test_st57_email_letter_case_does_not_matter_for_login(ui):
    """ST-57 Registering as Sam@USF.EDU and logging in as sam@usf.edu works."""
    email = unique_email("Sam", "USF.EDU")
    ui.register(email=email)
    ui.login(email.lower())
    assert ui.exists("nav button.linklike")
