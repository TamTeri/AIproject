"""QuoteService builds the server-owned quote from repository facts only."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.pricing.config import PricingUnavailable, temporary_local_policy
from app.pricing.service import CurrencyInfo, EventPrice, QuoteService, QuoteUnavailable


class FakePricingRepository:
    def __init__(self, email: str = "fan@example.com") -> None:
        self.email = email
        self.rates = {
            "USD": CurrencyInfo("USD", 2, Decimal("1")),
            "EUR": CurrencyInfo("EUR", 2, Decimal("0.92")),
        }

    def buyer_email(self, tx, buyer_id):
        return self.email if buyer_id == "1" else None

    def event_price(self, tx, event_id):
        return EventPrice(event_id, 2500, "usf") if event_id == "10" else None

    def currency(self, tx, code):
        return self.rates.get(code)

    def enabled_currencies(self, tx):
        return list(self.rates.values())


def service(email: str = "fan@example.com") -> QuoteService:
    return QuoteService(repository=FakePricingRepository(email), policy=temporary_local_policy())


def test_quote_for_regular_buyer_has_no_discount():
    quote = service().quote(tx=None, buyer_id="1", event_id="10", quantity=2, currency="USD")
    assert (quote.total_minor, quote.discount_minor, quote.discount_reason) == (
        5000,
        0,
        "domain_not_eligible",
    )


def test_quote_for_usf_student_applies_discount_and_records_policy_revision():
    quote = service("Student@USF.EDU").quote(tx=None, buyer_id="1", event_id="10", quantity=2, currency="EUR")
    assert quote.total_minor == 4140
    assert quote.discount_minor == 460
    assert quote.discount_reason == "eligible"
    assert quote.policy_revision == "temporary-local-v1"
    assert quote.exchange_rate == Decimal("0.92")


def test_quote_snapshot_round_trips_through_json():
    quote = service("a@usf.edu").quote(tx=None, buyer_id="1", event_id="10", quantity=1, currency="EUR")
    from app.purchase.models import QuoteSnapshot

    assert QuoteSnapshot.from_json(quote.to_json()) == quote


@pytest.mark.parametrize(
    ("buyer", "event", "currency"), [("2", "10", "USD"), ("1", "11", "USD"), ("1", "10", "GBP")]
)
def test_missing_facts_raise_quote_unavailable(buyer, event, currency):
    with pytest.raises(QuoteUnavailable):
        service().quote(tx=None, buyer_id=buyer, event_id=event, quantity=1, currency=currency)


def test_supported_currencies_come_from_configuration():
    assert service().supported_currencies(None) == {"USD", "EUR"}


@pytest.mark.parametrize("environment", ["production", "staging", "ci"])
def test_temporary_policy_fails_closed_outside_local_environments(environment):
    with pytest.raises(PricingUnavailable):
        temporary_local_policy().validate_for_environment(environment)
