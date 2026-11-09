"""Administrator-only rate management and audit viewer (admin-001..003, audit-003)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.admin.service import AdminService, AuditRow, NotAuthorized, RateRow, RateValidationError, parse_rate
from app.identity.contracts import Principal

ADMIN = Principal("1", "Admin", "admin@eventhub.test", role="administrator")
BUYER = Principal("2", "Buyer", "buyer@usf.edu")


class FakeAdminRepository:
    def __init__(self) -> None:
        self.rates = {"USD": Decimal("1"), "EUR": Decimal("0.92")}
        self.updates: list[tuple] = []
        self.history: list[tuple] = []
        self.attempts = [
            AuditRow(
                str(i),
                datetime(2026, 11, 1, tzinfo=UTC),
                "b@x.com",
                "Jazz",
                1,
                "USD",
                "success",
                "success",
                None,
            )
            for i in range(120, 0, -1)
        ]

    def list_rates(self):
        return [RateRow(code, rate, None, None) for code, rate in self.rates.items()]

    def currency_enabled(self, code):
        return code in self.rates

    def current_rate(self, code):
        return self.rates.get(code)

    def upsert_rate(self, *, currency, rate, admin_id, old_rate):
        self.rates[currency] = rate
        self.updates.append((currency, rate, admin_id))
        self.history.append((currency, old_rate, rate, admin_id))

    def list_attempts(self, *, limit, before_id):
        rows = [r for r in self.attempts if before_id is None or int(r.id) < int(before_id)]
        return rows[:limit]


@pytest.mark.parametrize("actor", [None, BUYER])
def test_non_admins_are_refused_everywhere(actor):
    repo = FakeAdminRepository()
    service = AdminService(repository=repo)
    with pytest.raises(NotAuthorized):
        service.list_rates(actor)
    with pytest.raises(NotAuthorized):
        service.set_rate(actor, currency="EUR", rate="1")
    assert repo.history == []
    with pytest.raises(NotAuthorized):
        service.audit_page(actor)


@pytest.mark.requirement("admin-006")
def test_admin_can_update_a_rate_and_it_records_who():
    repo = FakeAdminRepository()
    value = AdminService(repository=repo).set_rate(ADMIN, currency=" eur ", rate="0.95")
    assert value == Decimal("0.95")
    assert repo.updates == [("EUR", Decimal("0.95"), "1")]
    assert repo.history == [("EUR", Decimal("0.92"), Decimal("0.95"), "1")]


@pytest.mark.requirement("admin-006")
@pytest.mark.parametrize("raw", ["1.16", "0.68", "9.2", "0.092"])
def test_large_change_is_rejected_without_confirmation(raw):
    repo = FakeAdminRepository()
    with pytest.raises(RateValidationError, match="more than 25%"):
        AdminService(repository=repo).set_rate(ADMIN, currency="EUR", rate=raw)
    assert repo.history == [] and repo.rates["EUR"] == Decimal("0.92")


@pytest.mark.requirement("admin-006")
def test_large_change_is_accepted_with_confirmation_and_exact_25_percent_passes():
    repo = FakeAdminRepository()
    service = AdminService(repository=repo)
    service.set_rate(ADMIN, currency="EUR", rate="1.15")  # exactly +25%
    service.set_rate(ADMIN, currency="EUR", rate="11.5", confirm_large_change=True)
    assert [h[2] for h in repo.history] == [Decimal("1.15"), Decimal("11.5")]


@pytest.mark.requirement("admin-006")
def test_first_rate_for_a_currency_needs_no_confirmation():
    repo = FakeAdminRepository()
    repo.rates.pop("EUR")
    repo.currency_enabled = lambda code: True
    AdminService(repository=repo).set_rate(ADMIN, currency="EUR", rate="500")
    assert repo.history == [("EUR", None, Decimal("500"), "1")]


@pytest.mark.requirement("admin-006", "pricing-013")
@pytest.mark.parametrize(
    ("raw", "ok"),
    [
        ("0.12345678", True),
        ("0.123456789", False),
        ("100000", True),
        ("100000.00000001", False),
        ("0", False),
        ("-0.5", False),
        ("NaN", False),
        ("-Infinity", False),
        ("0,92", False),
    ],
)
def test_rate_boundaries(raw, ok):
    repo = FakeAdminRepository()
    service = AdminService(repository=repo)
    if ok:
        service.set_rate(ADMIN, currency="EUR", rate=raw, confirm_large_change=True)
        assert repo.rates["EUR"] == Decimal(raw)
    else:
        with pytest.raises(RateValidationError):
            service.set_rate(ADMIN, currency="EUR", rate=raw, confirm_large_change=True)
        assert repo.history == []


@pytest.mark.parametrize("raw", ["", "abc", "0", "-1", "1e9", "NaN", "Infinity", "0.123456789", "1" * 40])
def test_invalid_rates_are_rejected(raw):
    with pytest.raises(RateValidationError):
        parse_rate(raw)


def test_base_currency_and_unknown_currencies_cannot_be_changed():
    service = AdminService(repository=FakeAdminRepository())
    with pytest.raises(RateValidationError):
        service.set_rate(ADMIN, currency="USD", rate="2")
    with pytest.raises(RateValidationError):
        service.set_rate(ADMIN, currency="XYZ", rate="2")


def test_audit_viewer_pages_newest_first():
    service = AdminService(repository=FakeAdminRepository())
    first = service.audit_page(ADMIN)
    assert [r.id for r in first.rows[:2]] == ["120", "119"]
    assert len(first.rows) == 50
    second = service.audit_page(ADMIN, before_id=first.next_before_id)
    assert second.rows[0].id == "70"
    last = service.audit_page(ADMIN, before_id="21")
    assert last.next_before_id is None
