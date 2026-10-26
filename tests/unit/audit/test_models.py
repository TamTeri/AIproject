"""Audit records are bounded and map outcomes onto the database categories."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.audit.models import PurchaseAttemptAudit
from app.purchase.models import AuditCategory, PurchaseOutcome, audit_category

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def record(**overrides):
    values = dict(
        attempt_id="a1",
        submitted_at=NOW,
        buyer_id="1",
        event_id="2",
        quantity=1,
        currency="USD",
        outcome="success",
        reason_code="success",
    )
    values.update(overrides)
    return PurchaseAttemptAudit(**values)


def test_every_outcome_maps_to_an_allowed_database_category():
    allowed = {"success", "rejected", "failed", "replayed"}
    for outcome in PurchaseOutcome:
        assert str(audit_category(outcome)) in allowed


def test_specific_mappings():
    assert audit_category(PurchaseOutcome.SUCCESS) is AuditCategory.SUCCESS
    assert audit_category(PurchaseOutcome.SOLD_OUT) is AuditCategory.REJECTED
    assert audit_category(PurchaseOutcome.INVALID_QUANTITY) is AuditCategory.REJECTED
    assert audit_category(PurchaseOutcome.PAYMENT_FAILED) is AuditCategory.FAILED
    assert audit_category(PurchaseOutcome.INTERNAL_ERROR) is AuditCategory.FAILED


@pytest.mark.parametrize(
    "overrides",
    [
        {"submitted_at": datetime(2026, 11, 1)},  # no timezone
        {"currency": "U S D"},
        {"currency": "X" * 17},
        {"quantity": -1},
        {"quantity": True},
        {"outcome": "drop table;"},
        {"buyer_id": "x" * 200},
    ],
)
def test_unbounded_values_are_rejected(overrides):
    with pytest.raises(ValueError):
        record(**overrides)
