"""Administrator-only use cases (admin-001..003, audit-003, pricing-005).

Every method takes the acting Principal and refuses non-administrators, so
the rule holds even if a route forgets its decorator (defence in depth).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from app.identity.contracts import Principal

MAX_RATE = Decimal("100000")
MAX_RATE_PLACES = 8  # exchange_rates.rate is NUMERIC(18, 8)
AUDIT_PAGE_SIZE = 50


class NotAuthorized(PermissionError):
    pass


class RateValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RateRow:
    currency: str
    rate: Decimal
    updated_at: datetime | None
    updated_by: str | None


@dataclass(frozen=True)
class AuditRow:
    id: str
    submitted_at: datetime
    buyer_email: str | None
    event_title: str | None
    quantity: int | None
    currency: str | None
    outcome: str
    reason_code: str
    order_id: str | None


@dataclass(frozen=True)
class AuditPage:
    rows: list[AuditRow]
    next_before_id: str | None


class AdminRepository(Protocol):
    def list_rates(self) -> list[RateRow]: ...

    def currency_enabled(self, code: str) -> bool: ...

    def upsert_rate(self, *, currency: str, rate: Decimal, admin_id: str) -> None: ...

    def list_attempts(self, *, limit: int, before_id: str | None) -> list[AuditRow]: ...


def parse_rate(raw: str) -> Decimal:
    """Validate a rate typed by an administrator (admin-003)."""
    text = (raw or "").strip()
    if not text or len(text) > 32:
        raise RateValidationError("Enter a rate, for example 0.92.")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise RateValidationError("Rate must be a number.") from exc
    if not value.is_finite() or value <= 0 or value > MAX_RATE:
        raise RateValidationError(f"Rate must be greater than 0 and at most {MAX_RATE}.")
    if -value.as_tuple().exponent > MAX_RATE_PLACES:
        raise RateValidationError(f"Rate may have at most {MAX_RATE_PLACES} decimal places.")
    return value


class AdminService:
    def __init__(self, *, repository: AdminRepository, base_currency: str = "USD") -> None:
        self._repository = repository
        self._base = base_currency

    def list_rates(self, actor: Principal | None) -> list[RateRow]:
        _require_admin(actor)
        return self._repository.list_rates()

    def set_rate(self, actor: Principal | None, *, currency: str, rate: str) -> Decimal:
        _require_admin(actor)
        code = (currency or "").strip().upper()
        if code == self._base:
            raise RateValidationError(f"{self._base} is the base currency; its rate is always 1.")
        if not self._repository.currency_enabled(code):
            raise RateValidationError("Unknown or disabled currency.")
        value = parse_rate(rate)
        self._repository.upsert_rate(currency=code, rate=value, admin_id=actor.account_id)
        return value

    def audit_page(self, actor: Principal | None, *, before_id: str | None = None) -> AuditPage:
        _require_admin(actor)
        if before_id is not None and (not str(before_id).isdigit() or len(str(before_id)) > 18):
            before_id = None
        rows = self._repository.list_attempts(limit=AUDIT_PAGE_SIZE + 1, before_id=before_id)
        more = len(rows) > AUDIT_PAGE_SIZE
        rows = rows[:AUDIT_PAGE_SIZE]
        return AuditPage(rows=rows, next_before_id=rows[-1].id if more and rows else None)


def _require_admin(actor: Principal | None) -> None:
    if actor is None or not actor.is_admin:
        raise NotAuthorized("administrator role required")


__all__ = [
    "AdminRepository",
    "AdminService",
    "AuditPage",
    "AuditRow",
    "NotAuthorized",
    "RateRow",
    "RateValidationError",
    "parse_rate",
]
