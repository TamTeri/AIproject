"""Helpers for the Selenium system tests.

- ``EventHub``: a small page object. It only does what a person does in the
  browser (open pages, type, click) and reads what a person sees.
- ``Database``: test-data set-up and white-box checks. Black-box tests use it
  only to *arrange* data (for example an event with one ticket left); the
  assertions are about what the browser shows.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from sqlalchemy import create_engine, text

ADMIN_EMAIL = "admin@eventhub.test"
ADMIN_PASSWORD = "admin-pass-123"
PASSWORD = "password-123"
WAIT_SECONDS = float(os.environ.get("EVENTHUB_WAIT_SECONDS", "10"))

_REQUIREMENT_ID = re.compile(r"\*\*([a-z]+-\d{3})\*\*")


def known_requirement_ids(features_dir: Path) -> set[str]:
    ids: set[str] = set()
    for path in features_dir.glob("*/requirements.md"):
        ids.update(_REQUIREMENT_ID.findall(path.read_text(encoding="utf-8")))
    return ids


def unique_email(prefix: str = "buyer", domain: str = "example.com") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@{domain}"


# ----------------------------------------------------------------- browser


def make_driver(*, width: int = 1280, height: int = 900, mobile: bool = False) -> WebDriver:
    """Chrome by default; EVENTHUB_BROWSER=edge or firefox to switch."""
    name = os.environ.get("EVENTHUB_BROWSER", "chrome").lower()
    headed = os.environ.get("EVENTHUB_HEADED", "").lower() in {"1", "true", "yes"}
    if name == "firefox":
        options = webdriver.FirefoxOptions()
        if not headed:
            options.add_argument("-headless")
        driver = webdriver.Firefox(options=options)
        driver.set_window_size(width, height)
        return driver
    options = webdriver.EdgeOptions() if name == "edge" else webdriver.ChromeOptions()
    if not headed:
        options.add_argument("--headless=new")
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument("--disable-search-engine-choice-screen")
    options.add_argument("--no-first-run")
    if os.environ.get("CI"):
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
    if mobile:
        options.add_experimental_option(
            "mobileEmulation",
            {"deviceMetrics": {"width": width, "height": height, "pixelRatio": 2.0, "touch": True}},
        )
    driver = webdriver.Edge(options=options) if name == "edge" else webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver


@dataclass
class Account:
    name: str
    email: str
    password: str = PASSWORD


class EventHub:
    """What a buyer or administrator can do in the browser."""

    def __init__(self, driver: WebDriver, base_url: str) -> None:
        self.driver = driver
        self.base_url = base_url
        self.account: Account | None = None

    # ---------------------------------------------------------- navigation

    def go(self, path: str) -> EventHub:
        self.driver.get(self.base_url + path)
        return self

    @property
    def path(self) -> str:
        parsed = urlparse(self.driver.current_url)
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")

    def wait(self, seconds: float = WAIT_SECONDS) -> WebDriverWait:
        return WebDriverWait(self.driver, seconds)

    def wait_for_path(self, pattern: str, seconds: float = WAIT_SECONDS) -> str:
        regex = re.compile(pattern)
        try:
            self.wait(seconds).until(lambda _: regex.search(self.path))
        except TimeoutException as exc:
            raise AssertionError(f"expected URL matching {pattern!r}, still on {self.path!r}") from exc
        return self.path

    def find(self, css: str) -> WebElement:
        return self.wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))

    def find_all(self, css: str) -> list[WebElement]:
        return self.driver.find_elements(By.CSS_SELECTOR, css)

    def exists(self, css: str) -> bool:
        return bool(self.driver.find_elements(By.CSS_SELECTOR, css))

    def text(self, css: str) -> str:
        return self.find(css).text.strip()

    def page_text(self) -> str:
        return self.driver.find_element(By.TAG_NAME, "body").text

    def click(self, css: str) -> None:
        self.wait().until(EC.element_to_be_clickable((By.CSS_SELECTOR, css))).click()

    def click_button(self, label: str, *, navigates: bool = True) -> None:
        """Click the visible button whose text starts with ``label``.

        By default, wait until the browser has left the current page. Reading the
        page straight after a click can read the *old* page, or fail with "Node
        ... does not belong to the document" (Part 5, run 1, ST-36).
        """
        xpath = f"//main//button[starts-with(normalize-space(.), {_xpath_literal(label)})]"
        old_page = self.driver.find_element(By.TAG_NAME, "html")
        self.wait().until(EC.element_to_be_clickable((By.XPATH, xpath))).click()
        if navigates:
            try:
                self.wait().until(_page_left(old_page))
            except TimeoutException as exc:
                raise AssertionError(
                    f"clicking {label!r} did not load a new page (still {self.path})"
                ) from exc
            self.find("body")

    def submit_with(self, button: WebElement) -> None:
        """Click a form button you already found, and wait for the next page.

        Checking straight after a plain ``.click()`` races the page load: ST-68
        failed once in run 4 because it looked for the error before it appeared.
        """
        old_page = self.driver.find_element(By.TAG_NAME, "html")
        button.click()
        try:
            self.wait().until(_page_left(old_page))
        except TimeoutException as exc:
            raise AssertionError(f"the click did not load a new page (still {self.path})") from exc
        self.find("body")

    def type(self, css: str, value: str) -> None:
        field = self.find(css)
        field.clear()
        field.send_keys(value)

    def choose(self, css: str, value: str) -> None:
        Select(self.find(css)).select_by_value(value)

    def selected(self, css: str) -> str:
        return Select(self.find(css)).first_selected_option.get_attribute("value")

    def double_click(self, element: WebElement) -> None:
        ActionChains(self.driver).double_click(element).perform()

    # ------------------------------------------------------------ messages

    def error(self) -> str:
        return self.text(".error")

    def error_code(self) -> str:
        return self.find(".error").get_attribute("data-error-code") or ""

    def flash(self) -> str:
        return " ".join(e.text for e in self.find_all(".flash, .message")).strip()

    # ------------------------------------------------------------ identity

    def register(
        self, *, name: str = "Test Buyer", email: str | None = None, password: str = PASSWORD
    ) -> Account:
        account = Account(name=name, email=email or unique_email(), password=password)
        self.go("/register")
        self.type("#name", account.name)
        self.type("#email", account.email)
        self.type("#password", account.password)
        self.click_button("Create account")
        self.wait().until(lambda _: "Account created" in self.flash() or self.exists(".error"))
        assert "Account created" in self.flash(), self.page_text()
        return account

    def login(self, email: str, password: str = PASSWORD, *, next_path: str | None = None) -> None:
        self.go(f"/login?next={next_path}" if next_path else "/login")
        self.type("#email", email)
        self.type("#password", password)
        self.click_button("Log in")
        self.wait().until(lambda _: not self.path.startswith("/login") or self.exists(".error"))

    def register_and_login(self, **kwargs) -> Account:
        account = self.register(**kwargs)
        self.login(account.email, account.password)
        assert self.exists("nav button.linklike"), "expected to be logged in"
        self.account = account
        return account

    def logout(self) -> None:
        self.find("nav button.linklike").click()
        self.wait_for_path(r"^/events")

    # ------------------------------------------------------------- catalog

    def search(self, query: str) -> None:
        self.go("/events")
        self.type("#event-search", query)
        self.click(".search button")
        self.wait_for_path(r"^/events\?q=")

    def card_titles(self) -> list[str]:
        return [e.text.strip() for e in self.find_all(".event-card h2")]

    def card_for(self, artist: str) -> WebElement:
        for card in self.find_all(".event-card"):
            if card.find_element(By.CSS_SELECTOR, "h2").text.strip() == artist:
                return card
        raise AssertionError(f"no event card for {artist!r}; cards: {self.card_titles()}")

    # ------------------------------------------------------------ purchase

    def start_checkout(self, event_id: str, quantity: str = "1", currency: str | None = None) -> None:
        self.go(f"/events/{event_id}")
        self.type("#quantity", quantity)
        if currency:
            self.choose("#currency", currency)
        self.click_button("Continue to checkout")

    def tamper_quantity(self, value: str) -> None:
        """Bypass the browser's own number check, as a script or old browser would."""
        field = self.find("#quantity")
        self.driver.execute_script(
            "arguments[0].type = 'text'; arguments[0].removeAttribute('min');"
            "arguments[0].removeAttribute('required'); arguments[0].value = arguments[1];",
            field,
            value,
        )

    def tamper_currency(self, value: str) -> None:
        select = self.find("#currency")
        self.driver.execute_script(
            "var o = document.createElement('option'); o.value = arguments[1]; o.text = arguments[1];"
            "arguments[0].appendChild(o); arguments[0].value = arguments[1];",
            select,
            value,
        )

    def pay(self, choice: str = "approve") -> None:
        self.choose("#payment", choice)
        self.click_button("Pay ")

    def buy(self, event_id: str, quantity: str = "1", currency: str | None = None) -> str:
        """Standard checkout end to end. Returns the order confirmation path."""
        self.start_checkout(event_id, quantity, currency)
        self.wait_for_path(r"^/checkout/\d+$")
        self.pay("approve")
        return self.wait_for_path(r"^/orders/\d+")

    def summary(self) -> dict[str, str]:
        """The <dl class="summary"> on the current page as {label: value}."""
        labels = [e.text.strip() for e in self.find_all("dl.summary dt")]
        values = [e.text.strip() for e in self.find_all("dl.summary dd")]
        return dict(zip(labels, values, strict=False))

    def order_rows(self) -> list[str]:
        self.go("/orders")
        self.find("h1")
        return [row.text for row in self.find_all("tbody tr")]

    # --------------------------------------------------------------- admin

    def audit_rows(self, email: str) -> list[dict[str, str]]:
        """Audit log rows for one buyer, newest first (administrator browser)."""
        self.go("/admin/audit")
        self.find("h1")
        rows = []
        for row in self.find_all("tbody tr[data-outcome]"):
            cells = [c.text.strip() for c in row.find_elements(By.TAG_NAME, "td")]
            if len(cells) >= 9 and cells[2] == email:
                rows.append(
                    {
                        "outcome": row.get_attribute("data-outcome"),
                        "event": cells[3],
                        "quantity": cells[4],
                        "currency": cells[5],
                        "reason": cells[7],
                        "order": cells[8],
                    }
                )
        return rows


def _page_left(old_page: WebElement):
    """Wait condition: the page ``old_page`` belonged to has been replaced.

    Like ``EC.staleness_of``, but Chrome 150 reports a node from a page that has already navigated
    away as "Node with given id does not belong to the document" (an unknown-error WebDriverException)
    and not as a stale-element error. Both mean the old page is gone (ST-11 and ST-18 on Chrome 150).
    """

    def check(_driver) -> bool:
        try:
            old_page.is_enabled()
            return False
        except StaleElementReferenceException:
            return True
        except WebDriverException as exc:
            if "does not belong to the document" in str(exc):
                return True
            raise

    return check


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    return "concat('" + value.replace("'", "', \"'\", '") + "')"


# ---------------------------------------------------------------- database


class Database:
    """Arrange test data and read back what the system stored."""

    def __init__(self, url: str) -> None:
        self.engine = create_engine(url, pool_pre_ping=True)

    def dispose(self) -> None:
        self.engine.dispose()

    def scalar(self, sql: str, **params):
        with self.engine.begin() as connection:
            return connection.execute(text(sql), params).scalar()

    def rows(self, sql: str, **params) -> list[dict]:
        with self.engine.begin() as connection:
            return [dict(r) for r in connection.execute(text(sql), params).mappings().all()]

    def execute(self, sql: str, **params) -> int:
        with self.engine.begin() as connection:
            return connection.execute(text(sql), params).rowcount

    def create_event(
        self,
        *,
        artist: str | None = None,
        capacity: int = 50,
        price_minor: int = 2000,
        starts_in: timedelta = timedelta(days=30),
        venue: str = "System Test Hall",
        host_type: str = "usf",
    ) -> str:
        artist = artist or f"System Test Act {uuid.uuid4().hex[:6]}"
        return str(
            self.scalar(
                """
                INSERT INTO events (catalog_key, title, artist, venue, starts_at, host_type,
                                    base_price_minor, capacity)
                VALUES (:key, :title, :artist, :venue, CURRENT_TIMESTAMP + :starts_in, :host_type,
                        :price, :capacity)
                RETURNING id
                """,
                key=f"system-test-{uuid.uuid4().hex}",
                title=f"{artist} live",
                artist=artist,
                venue=venue,
                starts_in=starts_in,
                host_type=host_type,
                price=price_minor,
                capacity=capacity,
            )
        )

    def account_id(self, email: str) -> str:
        return str(self.scalar("SELECT id FROM accounts WHERE normalized_email = :e", e=email.lower()))

    def order_count(self, email: str, event_id: str | None = None) -> int:
        return int(
            self.scalar(
                """
                SELECT COUNT(*) FROM orders o JOIN accounts a ON a.id = o.buyer_id
                WHERE a.normalized_email = :e AND (CAST(:ev AS BIGINT) IS NULL OR o.event_id = CAST(:ev AS BIGINT))
                """,
                e=email.lower(),
                ev=event_id,
            )
        )

    def hold_count(self, email: str, status: str | None = None) -> int:
        return int(
            self.scalar(
                """
                SELECT COUNT(*) FROM holds h JOIN accounts a ON a.id = h.buyer_id
                WHERE a.normalized_email = :e AND (CAST(:s AS TEXT) IS NULL OR h.status = :s)
                """,
                e=email.lower(),
                s=status,
            )
        )

    def available(self, event_id: str) -> int:
        return int(
            self.scalar(
                "SELECT available_quantity FROM event_availability WHERE event_id = :id", id=int(event_id)
            )
        )

    def audit_reasons(self, *, email: str | None = None, event_id: str | None = None) -> list[str]:
        rows = self.rows(
            """
            SELECT p.reason_code FROM purchase_attempts p
            LEFT JOIN accounts a ON a.id = p.buyer_id
            WHERE (CAST(:e AS TEXT) IS NULL OR a.normalized_email = :e)
              AND (CAST(:ev AS BIGINT) IS NULL OR p.event_id = CAST(:ev AS BIGINT))
            ORDER BY p.id
            """,
            e=email.lower() if email else None,
            ev=event_id,
        )
        return [r["reason_code"] for r in rows]

    def expire_hold(self, hold_id: str) -> None:
        """White-box: make a hold's ten minutes run out now, without waiting."""
        self.execute(
            """
            UPDATE holds SET created_at = CURRENT_TIMESTAMP - INTERVAL '11 minutes',
                             expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'
            WHERE id = :id
            """,
            id=int(hold_id),
        )

    def idle_sessions(self, email: str, minutes: int = 31) -> None:
        """White-box: pretend the buyer has been idle for ``minutes``."""
        self.execute(
            """
            UPDATE account_sessions SET created_at = CURRENT_TIMESTAMP - make_interval(mins => :m),
                                        last_seen_at = CURRENT_TIMESTAMP - make_interval(mins => :m)
            WHERE account_id = (SELECT id FROM accounts WHERE normalized_email = :e)
            """,
            m=minutes,
            e=email.lower(),
        )

    def rate(self, currency: str) -> str:
        return str(self.scalar("SELECT rate FROM exchange_rates WHERE currency_code = :c", c=currency))

    def set_rate(self, currency: str, rate: str) -> None:
        self.execute("UPDATE exchange_rates SET rate = :r WHERE currency_code = :c", r=rate, c=currency)
