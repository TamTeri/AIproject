"""Real-browser check of a running EventHub (Google Chrome via Playwright).

Optional: needs Chrome and `pip install playwright`. It RESETS the database in
DATABASE_URL (local/dev only), seeds it, creates an admin, then clicks through
15 scenarios. Start the server first in another terminal:

    export DATABASE_URL='postgresql+psycopg://eventhub:eventhub@localhost:55432/eventhub_test'
    EVENTHUB_ENVIRONMENT=development .venv/bin/flask --app 'app:create_app()' run --port 5055
    .venv/bin/python scripts/browser_check.py      # screenshots go to browser-shots/
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("EVENTHUB_BASE_URL", "http://127.0.0.1:5055")
ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "browser-shots"
SHOTS.mkdir(exist_ok=True)
results: list[tuple[str, bool, str]] = []
console_errors: list[str] = []


def check(name: str, fn) -> None:
    try:
        detail = fn() or ""
        results.append((name, True, str(detail)))
    except Exception as exc:  # report and continue
        results.append((name, False, f"{type(exc).__name__}: {exc}"[:300]))


env = dict(
    os.environ,
    EVENTHUB_ENVIRONMENT="development",
    EVENTHUB_RESET_ENABLED="true",
    EVENTHUB_ADMIN_EMAIL="admin@eventhub.test",
    EVENTHUB_ADMIN_PASSWORD="admin-pass-123",
)
if "DATABASE_URL" not in env:
    sys.exit("Set DATABASE_URL to the same throwaway database the server uses.")
for command in ("reset", "seed", "create-admin"):
    subprocess.run([sys.executable, "-m", "app.db.commands", command], check=True, env=env, cwd=ROOT)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    # Intentional 4xx pages (403/404/409) log "Failed to load resource"; only real JS errors count.
    page.on(
        "console",
        lambda m: (
            console_errors.append(m.text)
            if m.type == "error" and "Failed to load resource" not in m.text
            else None
        ),
    )
    page.on("pageerror", lambda e: console_errors.append(str(e)))

    def protected_redirect():
        page.goto(f"{BASE}/orders")
        assert "/login?next=/orders" in page.url, page.url

    def register_and_login():
        page.goto(f"{BASE}/register")
        page.fill("#name", "Sam Student")
        page.fill("#email", "Sam@USF.edu")
        page.fill("#password", "password-123")
        page.click("button[type=submit]")
        expect(page.locator(".flash")).to_contain_text("Account created")
        page.goto(f"{BASE}/login?next=/orders")
        page.fill("#email", "sam@usf.edu")
        page.fill("#password", "password-123")
        page.click("main button[type=submit]")
        assert page.url.endswith("/orders"), page.url
        expect(page.locator("nav")).to_contain_text("Log out (Sam Student)")

    def search():
        page.goto(f"{BASE}/events")
        page.fill("#event-search", "arena")
        page.click(".search button")
        n = page.locator(".event-card").count()
        assert n == 2, n
        page.fill("#event-search", "polka")
        page.click(".search button")
        expect(page.locator(".message")).to_contain_text("No events matched")
        assert page.locator(".event-card").count() == 6
        page.screenshot(path=str(SHOTS / "events.png"), full_page=True)

    def single_click_opens_event():
        page.goto(f"{BASE}/events")
        page.locator(".event-card").nth(1).locator("p.muted").click()  # click card body, not the link
        page.wait_for_url(re.compile(r"/events/\d+$"), timeout=3000)
        expect(page.locator("h1")).to_have_text("Bulls Jazz Ensemble")
        expect(page.locator("dl.summary")).to_contain_text("tickets left")
        return page.url

    def double_click_quick_buys():
        page.goto(f"{BASE}/events")
        page.locator(".event-card").nth(0).locator("p.muted").dblclick()
        page.wait_for_url(re.compile(r"/orders/\d+\?confirmed=1"), timeout=5000)
        expect(page.locator("h1")).to_have_text("Order confirmed")
        total = page.locator("dd.total").inner_text()
        assert total == "22.50 USD", total  # 25.00 USD minus 10% student discount
        page.screenshot(path=str(SHOTS / "quickbuy-confirmation.png"), full_page=True)
        return total

    def checkout_decline_then_approve():
        page.goto(f"{BASE}/events/2")
        page.fill("#quantity", "2")
        page.select_option("#currency", "EUR")
        page.click("text=Continue to checkout")
        page.wait_for_url(re.compile(r"/checkout/\d+$"))
        expect(page.locator("dd.total")).to_have_text("24.84 EUR")  # 30 USD -10% = 27 x 0.92
        page.screenshot(path=str(SHOTS / "checkout.png"), full_page=True)
        page.select_option("#payment", "decline")
        page.click('button:has-text("Pay ")')
        expect(page.locator(".error")).to_contain_text("declined")
        page.goto(f"{BASE}/events/2")
        expect(page.locator("dl.summary")).to_contain_text("250")  # tickets released
        page.fill("#quantity", "2")
        page.select_option("#currency", "EUR")
        page.click("text=Continue to checkout")
        page.wait_for_url(re.compile(r"/checkout/\d+$"))
        page.click('button:has-text("Pay ")')
        page.wait_for_url(re.compile(r"/orders/\d+\?confirmed=1"))
        expect(page.locator("dl.summary")).to_contain_text("0.92 EUR per USD")
        expect(page.locator("dd.total")).to_have_text("24.84 EUR")

    def validation_messages():
        page.goto(f"{BASE}/events/1")
        page.fill("#quantity", "10")
        page.click("text=Continue to checkout")
        expect(page.locator(".error")).to_contain_text("ticket limit")
        page.goto(f"{BASE}/events/6")
        page.fill("#quantity", "3")
        page.click("text=Continue to checkout")
        expect(page.locator(".error")).to_contain_text("not enough tickets")

    def cancel_releases():
        page.goto(f"{BASE}/events/6")
        page.fill("#quantity", "2")
        page.click("text=Continue to checkout")
        page.wait_for_url(re.compile(r"/checkout/\d+$"))
        page.click("text=Cancel and release tickets")
        expect(page.locator(".flash")).to_contain_text("released")
        page.goto(f"{BASE}/events/6")
        expect(page.locator("dl.summary")).to_contain_text("2 tickets left")

    def order_history_reopens():
        page.goto(f"{BASE}/orders")
        rows = page.locator("tbody tr").count()
        assert rows == 2, rows
        page.locator("tbody tr a").first.click()
        expect(page.locator("h1")).to_have_text("Order confirmed")
        return f"{rows} orders"

    def saved_currency_quick_buy_button():
        page.goto(f"{BASE}/account")
        page.select_option("#currency", "GBP")
        page.click("main button[type=submit]")
        page.goto(f"{BASE}/events/3")
        page.click("text=Quick Buy")
        page.wait_for_url(re.compile(r"/orders/\d+\?confirmed=1"))
        expect(page.locator("dd.total")).to_have_text(
            "32.00 GBP"
        )  # 45 -10% = 40.50 x 0.79 = 31.995 -> half-up 32.00
        return page.locator("dd.total").inner_text()

    def buyer_blocked_from_admin():
        resp = page.goto(f"{BASE}/admin/audit")
        assert resp.status == 403, resp.status

    def other_buyer_cannot_see_order():
        other = browser.new_context().new_page()
        other.goto(f"{BASE}/register")
        other.fill("#name", "Other")
        other.fill("#email", "other@example.com")
        other.fill("#password", "password-123")
        other.click("button[type=submit]")
        other.goto(f"{BASE}/login")
        other.fill("#email", "other@example.com")
        other.fill("#password", "password-123")
        other.click("main button[type=submit]")
        resp = other.goto(f"{BASE}/orders/1")
        assert resp.status == 404, resp.status
        other.context.close()

    def logout():
        page.click("text=Log out")
        page.goto(f"{BASE}/orders")
        assert "/login" in page.url

    def admin_flow():
        admin = browser.new_context().new_page()
        admin.on("pageerror", lambda e: console_errors.append(str(e)))
        admin.goto(f"{BASE}/login")
        admin.fill("#email", "admin@eventhub.test")
        admin.fill("#password", "admin-pass-123")
        admin.click("main button[type=submit]")
        admin.goto(f"{BASE}/admin/audit")
        outcomes = admin.locator("tbody tr").evaluate_all("rows => rows.map(r => r.dataset.outcome)")
        admin.screenshot(path=str(SHOTS / "admin-audit.png"), full_page=True)
        assert "success" in outcomes and "rejected" in outcomes and "failed" in outcomes, outcomes
        admin.goto(f"{BASE}/admin/rates")
        row = admin.locator("tr", has_text="EUR")
        row.locator("input[name=rate]").fill("-1")
        row.locator("button").click()
        expect(admin.locator(".error")).to_contain_text("greater than 0")
        row = admin.locator("tr", has_text="EUR")
        row.locator("input[name=rate]").fill("0.95")
        row.locator("button").click()
        expect(admin.locator(".flash")).to_contain_text("saved")
        expect(admin.locator("tr", has_text="EUR")).to_contain_text("admin@eventhub.test")
        admin.context.close()
        return f"{len(outcomes)} audit rows: {sorted(set(outcomes))}"

    def phone_layout():
        phone = browser.new_context(
            viewport={"width": 375, "height": 800}, is_mobile=True, has_touch=True
        ).new_page()
        for path in ("/events", "/events/1", "/login", "/register"):
            phone.goto(f"{BASE}{path}")
            overflow = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            assert overflow <= 0, f"{path} scrolls sideways by {overflow}px"
        phone.goto(f"{BASE}/events")
        phone.screenshot(path=str(SHOTS / "phone-events.png"), full_page=True)
        phone.context.close()

    for name, fn in [
        ("protected page redirects to login", protected_redirect),
        ("register + login + return to page", register_and_login),
        ("search artist/venue + no-match", search),
        ("single click on card opens event", single_click_opens_event),
        ("double click on card = quick buy", double_click_quick_buys),
        ("checkout EUR: decline, then approve", checkout_decline_then_approve),
        ("limit and sold-out messages", validation_messages),
        ("cancel releases held tickets", cancel_releases),
        ("order history reopens confirmation", order_history_reopens),
        ("saved currency + Quick Buy button", saved_currency_quick_buy_button),
        ("buyer gets 403 on admin", buyer_blocked_from_admin),
        ("other buyer cannot open my order", other_buyer_cannot_see_order),
        ("logout ends session", logout),
        ("admin: audit log + rate update", admin_flow),
        ("phone width: no sideways scroll", phone_layout),
    ]:
        check(name, fn)
    browser.close()

for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
print("console/JS errors:", console_errors or "none")
sys.exit(0 if all(ok for _, ok, _ in results) and not console_errors else 1)
