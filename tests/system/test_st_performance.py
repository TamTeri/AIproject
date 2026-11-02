"""system-013 (Call 5): the performance sentence, as a pass/fail test.

Thuy: "I can generate load against the purchase path; I cannot tell you pass or
fail without a number." Until Marcus supplies the sentence, system-013 holds a
[TEMPORARY_MVP_DEFAULT]: with 20 buyers purchasing at the same time, 95% of
purchase requests finish within 1 second and none fails with a server error.

This test talks HTTP directly (no browser) so it measures the server, not Chrome.
The numbers below are the only place the target lives in the test suite.
"""

from __future__ import annotations

import http.cookiejar
import os
import re
import statistics
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

import pytest

from tests.system.support import PASSWORD, unique_email

pytestmark = [pytest.mark.system, pytest.mark.performance]

CONCURRENT_BUYERS = int(os.environ.get("EVENTHUB_PERF_BUYERS", "20"))
PURCHASES_PER_BUYER = int(os.environ.get("EVENTHUB_PERF_PURCHASES", "3"))
P95_TARGET_SECONDS = float(os.environ.get("EVENTHUB_PERF_P95_SECONDS", "1.0"))

_TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')
_KEY = re.compile(r'name="idempotency_key" value="([^"]+)"')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@dataclass
class _Buyer:
    base_url: str
    timings: list[float] = field(default_factory=list)
    statuses: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _NoRedirect())

    def request(self, path: str, data: dict | None = None) -> tuple[int, str, str]:
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        try:
            response = self.opener.open(self.base_url + path, data=body, timeout=30)
            return response.status, response.read().decode(), response.headers.get("Location", "")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode(errors="replace"), error.headers.get("Location", "")

    def form_fields(self, path: str, form_marker: str) -> dict[str, str]:
        _, page, _ = self.request(path)
        start = page.index(form_marker)
        chunk = page[start : start + 2000]
        fields = {"csrf_token": _TOKEN.search(chunk).group(1)}
        key = _KEY.search(chunk)
        if key:
            fields["idempotency_key"] = key.group(1)
        return fields

    def timed(self, path: str, data: dict) -> tuple[int, str, str]:
        started = time.perf_counter()
        result = self.request(path, data)
        self.timings.append(time.perf_counter() - started)
        self.statuses.append(result[0])
        return result

    def sign_up(self) -> None:
        email = unique_email("load")
        token = self.form_fields("/register", 'action="/register"')
        self.request("/register", {**token, "name": "Load Buyer", "email": email, "password": PASSWORD})
        token = self.form_fields("/login", 'action="/login"')
        status, _, _ = self.request("/login", {**token, "email": email, "password": PASSWORD})
        assert status == 302, f"login failed with {status}"

    def buy_one(self, event_id: str) -> None:
        fields = self.form_fields(f"/events/{event_id}", "/checkout")
        status, _, location = self.timed(
            f"/events/{event_id}/checkout", {**fields, "quantity": "1", "currency": "EUR"}
        )
        assert status == 302 and "/checkout/" in location, (status, location)
        hold_path = urllib.parse.urlparse(location).path
        fields = self.form_fields(hold_path, "/pay")
        status, _, location = self.timed(f"{hold_path}/pay", {**fields, "payment": "approve"})
        assert status == 302 and "/orders/" in location, (status, location)


@pytest.mark.requirement("system-013", "inventory-004")
def test_st70_twenty_buyers_at_once_meet_the_performance_target(base_url, db, record_property):
    """ST-70 20 simultaneous buyers: 95% of purchase requests finish within 1 s and none fails."""
    events = [db.create_event(capacity=1000) for _ in range(PURCHASES_PER_BUYER)]
    buyers = [_Buyer(base_url) for _ in range(CONCURRENT_BUYERS)]
    for buyer in buyers:
        buyer.sign_up()  # set-up, not measured

    errors: list[BaseException] = []
    start = threading.Barrier(len(buyers))

    def run(buyer: _Buyer) -> None:
        try:
            start.wait()
            for event_id in events:
                buyer.buy_one(event_id)
        except BaseException as exc:  # collected and reported below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(b,)) for b in buyers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    timings = sorted(t for b in buyers for t in b.timings)
    statuses = [s for b in buyers for s in b.statuses]
    p95 = timings[max(0, int(len(timings) * 0.95) - 1)] if timings else float("inf")
    print(
        f"\nperformance: {len(timings)} purchase requests from {CONCURRENT_BUYERS} buyers; "
        f"median {statistics.median(timings):.3f}s, p95 {p95:.3f}s, max {timings[-1]:.3f}s "
        f"(target p95 <= {P95_TARGET_SECONDS:.2f}s)"
    )
    record_property("purchase_requests", len(timings))
    record_property("median_seconds", round(statistics.median(timings), 3))
    record_property("p95_seconds", round(p95, 3))
    record_property("max_seconds", round(timings[-1], 3))
    record_property("p95_target_seconds", P95_TARGET_SECONDS)
    assert not errors, errors[:3]
    assert not [s for s in statuses if s >= 500], "server errors under load"
    assert len(timings) == CONCURRENT_BUYERS * PURCHASES_PER_BUYER * 2
    assert p95 <= P95_TARGET_SECONDS, f"p95 {p95:.3f}s is over the {P95_TARGET_SECONDS}s target"
    for event_id in events:
        assert db.available(event_id) == 1000 - CONCURRENT_BUYERS
