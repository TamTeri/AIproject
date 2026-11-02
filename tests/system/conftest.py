"""Selenium system tests: a real browser drives the real EventHub application.

One command runs everything (see scripts/run_system_tests.py):

1. the throwaway PostgreSQL in EVENTHUB_TEST_DATABASE_URL is reset, seeded and
   given an administrator;
2. create_app() is served on a free localhost port in a background thread
   (or set EVENTHUB_BASE_URL to test a server that is already running);
3. Chrome (headless unless EVENTHUB_HEADED=1; EVENTHUB_BROWSER=edge|firefox to
   switch) is driven through each test;
4. pytest-html writes reports/system-tests.html, with a screenshot of the
   browser for every failure.

Call 5 (Thuy, Priya): every test names the requirement it proves with
@pytest.mark.requirement("<id>", ...). A test without one, or with an id that is
not in features/*/requirements.md, stops the run (system-015).
"""

from __future__ import annotations

import html
import logging
import os
import re
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.system.support import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    Database,
    EventHub,
    known_requirement_ids,
    make_driver,
)

ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS = ROOT / "reports" / "screenshots"


def _is_system_test(item) -> bool:
    return "tests/system/" in item.nodeid.replace("\\", "/")


def _requirement_ids(item) -> list[str]:
    return [i for mark in item.iter_markers("requirement") for i in mark.args]


def _kind(item) -> str:
    return "white-box" if item.get_closest_marker("whitebox") else "black-box"


# ------------------------------------------------------------ traceability


def pytest_collection_modifyitems(config, items):
    """system-015: every system test must name at least one real requirement."""
    known = known_requirement_ids(ROOT / "features")
    problems = []
    for item in items:
        if not _is_system_test(item):
            continue
        ids = _requirement_ids(item)
        if not ids:
            problems.append(f"{item.nodeid}: no @pytest.mark.requirement(...)")
        unknown = [i for i in ids if i not in known]
        if unknown:
            problems.append(f"{item.nodeid}: unknown requirement id(s) {unknown}")
        item.user_properties.append(("requirements", " ".join(ids)))
        item.user_properties.append(("kind", _kind(item)))
    if problems:
        raise pytest.UsageError("System tests must trace to the specification:\n  " + "\n  ".join(problems))


# ----------------------------------------------------------------- server


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("EVENTHUB_TEST_DATABASE_URL")
    if not url:
        pytest.skip("EVENTHUB_TEST_DATABASE_URL is required for system tests (see README)")
    return url


@pytest.fixture(scope="session")
def db(database_url) -> Iterator[Database]:
    """Fresh, seeded database with one administrator, once per run."""
    from app.db.commands import create_admin
    from app.db.operations import reset_database, seed_database

    reset_database(database_url, environment="test", reset_enabled=True)
    seed_database(database_url)
    os.environ["EVENTHUB_ADMIN_EMAIL"] = ADMIN_EMAIL
    os.environ["EVENTHUB_ADMIN_PASSWORD"] = ADMIN_PASSWORD
    create_admin(database_url)
    database = Database(database_url)
    yield database
    database.dispose()


@pytest.fixture(scope="session")
def base_url(db, database_url) -> Iterator[str]:
    external = os.environ.get("EVENTHUB_BASE_URL")
    if external:
        yield external.rstrip("/")
        return

    from werkzeug.serving import make_server

    from app import create_app

    app = create_app(
        {
            "DATABASE_URL": database_url,
            "EVENTHUB_ENVIRONMENT": "test",
            "SECRET_KEY": "eventhub-system-tests",
        }
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, name="eventhub-under-test", daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=5)


# ---------------------------------------------------------------- browsers


@pytest.fixture(scope="session")
def _browser_pool() -> Iterator[dict[tuple, list]]:
    """Browsers kept open between tests. Starting and quitting Chrome took about
    4 of the 5 seconds per test in run 2, so finished browsers are wiped and reused."""
    pool: dict[tuple, list] = {}
    yield pool
    for drivers in pool.values():
        for driver in drivers:
            try:
                driver.quit()
            except Exception:  # pragma: no cover - the browser may already be gone
                pass


def _wipe(driver, base_url: str) -> bool:
    """Make a used browser look brand new to EventHub: no cookies, blank page."""
    try:
        driver.get(base_url + "/healthz")
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
        driver.get("about:blank")
        return not driver.get_cookies()
    except Exception:
        return False


@pytest.fixture
def browser_factory(request, base_url, _browser_pool) -> Iterator[Callable[..., EventHub]]:
    """Open as many independent browsers (separate cookie jars) as a test needs."""
    opened: list[tuple[tuple, EventHub]] = []
    hubs: list[EventHub] = []  # the same list the failure-screenshot hook reads

    def open_browser(**options) -> EventHub:
        key = tuple(sorted(options.items()))
        spare = _browser_pool.setdefault(key, [])
        driver = spare.pop() if spare else make_driver(**options)
        hub = EventHub(driver, base_url)
        opened.append((key, hub))
        hubs.append(hub)
        return hub

    request.node._eventhub_browsers = hubs
    yield open_browser
    for key, hub in opened:
        if _wipe(hub.driver, base_url):
            _browser_pool.setdefault(key, []).append(hub.driver)
        else:
            try:
                hub.driver.quit()
            except Exception:  # pragma: no cover - the browser may already be gone
                pass


@pytest.fixture
def ui(browser_factory) -> EventHub:
    """The main browser for a test."""
    return browser_factory()


@pytest.fixture
def admin_ui(browser_factory) -> EventHub:
    hub = browser_factory()
    hub.login(ADMIN_EMAIL, ADMIN_PASSWORD)
    return hub


# ------------------------------------------------------------- reporting


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if not _is_system_test(item):
        return
    report.requirements = " ".join(_requirement_ids(item))
    report.kind = _kind(item)
    doc = (getattr(item, "function", None) and item.function.__doc__) or ""
    report.case_title = doc.strip().splitlines()[0] if doc.strip() else ""
    if report.when != "call" or not report.failed:
        return
    browsers = getattr(item, "_eventhub_browsers", [])
    if not browsers:
        return
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    extras = list(getattr(report, "extras", []))
    try:
        from pytest_html import extras as html_extras
    except ImportError:  # pragma: no cover - pytest-html is optional
        html_extras = None
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", item.nodeid.split("::")[-1])[:80]
    for index, hub in enumerate(browsers):
        try:
            hub.driver.save_screenshot(str(SCREENSHOTS / f"{name}-{index}.png"))
            if html_extras is not None:
                extras.append(html_extras.png(hub.driver.get_screenshot_as_base64(), f"browser {index}"))
                extras.append(html_extras.url(hub.driver.current_url, f"browser {index} URL"))
        except Exception:  # pragma: no cover - a crashed browser cannot take screenshots
            pass
    report.extras = extras


class _HtmlReportColumns:
    """Adds Requirements / Kind / Test case columns to the pytest-html report."""

    def pytest_html_report_title(self, report):
        report.title = "EventHub system test report (Selenium)"

    def pytest_html_results_table_header(self, cells):
        cells.insert(2, "<th>Requirements</th>")
        cells.insert(3, "<th>Kind</th>")
        cells.insert(4, "<th>Test case</th>")

    def pytest_html_results_table_row(self, report, cells):
        cells.insert(2, f"<td>{html.escape(getattr(report, 'requirements', ''))}</td>")
        cells.insert(3, f"<td>{html.escape(getattr(report, 'kind', ''))}</td>")
        cells.insert(4, f"<td>{html.escape(getattr(report, 'case_title', ''))}</td>")


def pytest_configure(config):
    if config.pluginmanager.hasplugin("html"):
        config.pluginmanager.register(_HtmlReportColumns(), "eventhub-html-columns")
