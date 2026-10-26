"""Composition root: connects every feature to PostgreSQL for the web layer.

Feature packages never import each other's adapters; only this file does.
The web blueprint only sees the small port objects built here, which is why
the contract tests can swap them all for fakes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.admin.postgres import PostgresAdminRepository
from app.admin.service import AdminService, NotAuthorized, RateValidationError
from app.audit.postgres import PostgresAuditLog
from app.catalog.postgres import PostgresCatalogRepository
from app.catalog.service import CatalogService
from app.db.transaction import PostgresDatabase, SqlTransactionProvider, db_id, unit_of_work
from app.identity.contracts import LoginInput, Principal, RegisterInput
from app.identity.policy import SessionPolicy
from app.identity.postgres import PostgresAccountRepository, PostgresSessionRepository
from app.identity.service import (
    EmailAlreadyRegistered,
    IdentityService,
    InvalidCredentials,
    RegistrationValidationError,
)
from app.identity.sessions import SessionService
from app.inventory.postgres import PostgresInventory
from app.orders.postgres import PostgresOrderReader, PostgresOrderWriter
from app.orders.service import OrderHistoryService
from app.pricing.calculator import format_minor
from app.pricing.config import PricingPolicy, PricingUnavailable, temporary_local_policy
from app.pricing.postgres import PostgresPricingRepository
from app.pricing.service import QuoteService
from app.purchase.models import PaymentRequest, PurchasePolicy, PurchaseRequest
from app.purchase.postgres import (
    PostgresClock,
    PostgresPurchasableEvents,
    PostgresPurchaseLimits,
    SessionBuyer,
    SimulatedPayments,
)
from app.purchase.service import PurchaseCoordinator
from app.web.services import ServiceError, WebServices, unavailable_service


def _now() -> datetime:
    return datetime.now(UTC)


class IdentityAdapter:
    def __init__(self, database: PostgresDatabase, session_policy: SessionPolicy) -> None:
        self._db = database
        self._session_policy = session_policy

    def _service(self, tx) -> IdentityService:
        return IdentityService(account_repository=PostgresAccountRepository(tx))

    def register(self, *, name: str, email: str, password: str):
        try:
            with unit_of_work(self._db) as tx:
                return self._service(tx).register(
                    RegisterInput(name=name, email=email, password=password), now=_now()
                )
        except RegistrationValidationError as exc:
            raise ServiceError("invalid-registration", _sentence(str(exc)), 400) from exc
        except EmailAlreadyRegistered as exc:
            raise ServiceError("email-taken", "An account with this email already exists.", 409) from exc

    def authenticate(self, *, email: str, password: str) -> Principal:
        try:
            with unit_of_work(self._db) as tx:
                principal = self._service(tx).authenticate(LoginInput(email=email, password=password))
                PostgresAccountRepository(tx).mark_authenticated(principal.account_id, _now())
                return principal
        except InvalidCredentials as exc:
            raise ServiceError("invalid-credentials", "Invalid email or password.", 401) from exc

    def start_session(self, *, account_id: str) -> str:
        with unit_of_work(self._db) as tx:
            sessions = SessionService(repository=PostgresSessionRepository(tx), policy=self._session_policy)
            return sessions.start(account_id, now=_now())

    def resolve_session(self, *, token: str | None) -> Principal | None:
        if not token:
            return None
        with unit_of_work(self._db) as tx:
            sessions = SessionService(repository=PostgresSessionRepository(tx), policy=self._session_policy)
            account_id = sessions.resolve(token, now=_now())
            return self._service(tx).principal(account_id) if account_id else None

    def end_session(self, *, token: str | None) -> None:
        with unit_of_work(self._db) as tx:
            SessionService(repository=PostgresSessionRepository(tx), policy=self._session_policy).end(
                token, now=_now()
            )

    def set_preferred_currency(self, *, account_id: str, currency: str) -> None:
        code = (currency or "").strip().upper()
        with unit_of_work(self._db) as tx:
            if code not in {c.code for c in PostgresPricingRepository().enabled_currencies(tx)}:
                raise ServiceError("unsupported-currency", "That currency is not supported.", 400)
            PostgresAccountRepository(tx).set_preferred_currency(account_id, code)


class CatalogAdapter:
    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    def list_events(self, *, query: str | None = None):
        with unit_of_work(self._db) as tx:
            return CatalogService(repository=PostgresCatalogRepository(tx)).list_events(query=query)

    def get_event(self, *, event_id: str):
        with unit_of_work(self._db) as tx:
            return CatalogService(repository=PostgresCatalogRepository(tx)).get_event(event_id=event_id)


class PricingAdapter:
    def __init__(self, database: PostgresDatabase, policy: PricingPolicy) -> None:
        self._db = database
        self._policy = policy

    def currencies(self) -> list[str]:
        with unit_of_work(self._db) as tx:
            return [c.code for c in PostgresPricingRepository().enabled_currencies(tx)]

    def base_price_display(self, *, base_price_minor: int) -> str:
        return format_minor(base_price_minor, self._policy.currency_code, self._policy.currency_exponent)

    @property
    def discount_percent(self) -> str:
        return f"{self._policy.discount_percent.normalize():f}"

    @property
    def eligibility_domain(self) -> str:
        return self._policy.eligibility_domain


@dataclass
class HoldView:
    hold_id: str
    event_id: str
    event_title: str
    quantity: int
    currency: str
    subtotal: str
    discount: str
    discount_applied: bool
    total: str
    exchange_rate: str
    expires_at: datetime
    status: str


class CheckoutAdapter:
    """Standard checkout and quick buy. Both go through PurchaseCoordinator."""

    def __init__(
        self, database: PostgresDatabase, pricing_policy: PricingPolicy, purchase_policy: PurchasePolicy
    ) -> None:
        self._db = database
        self._quotes = QuoteService(repository=PostgresPricingRepository(), policy=pricing_policy)
        self._purchase_policy = purchase_policy
        self._inventory = PostgresInventory()

    def _coordinator(self, buyer_id: str) -> PurchaseCoordinator:
        return PurchaseCoordinator(
            transactions=SqlTransactionProvider(self._db),
            identity=SessionBuyer(buyer_id),
            database_time=PostgresClock(),
            quotes=self._quotes,
            inventory=self._inventory,
            payments=SimulatedPayments(),
            orders=PostgresOrderWriter(),
            audit=PostgresAuditLog(),
            events=PostgresPurchasableEvents(),
            limits=PostgresPurchaseLimits(),
            policy=self._purchase_policy,
        )

    def start(self, *, buyer_id: str, event_id: str, quantity: Any, currency: Any):
        return self._coordinator(buyer_id).start_checkout(
            PurchaseRequest(event_id=str(event_id), quantity=quantity, currency=currency)
        )

    def review(self, *, buyer_id: str, hold_id: str) -> HoldView | None:
        with unit_of_work(self._db) as tx:
            hold = self._inventory.get_hold_for_buyer(tx=tx, hold_id=hold_id, buyer_id=buyer_id)
            if hold is None or hold.quote_snapshot is None:
                return None
            event = tx.fetch_one("SELECT title FROM events WHERE id = :id", {"id": db_id(hold.event_id)})
        q = hold.quote_snapshot
        exp = q.currency_exponent
        subtotal = q.subtotal_minor if q.subtotal_minor is not None else q.total_minor + q.discount_minor
        return HoldView(
            hold_id=hold.id,
            event_id=hold.event_id,
            event_title=event["title"] if event else "",
            quantity=hold.quantity,
            currency=q.currency,
            subtotal=format_minor(subtotal, q.currency, exp),
            discount=format_minor(q.discount_minor, q.currency, exp),
            discount_applied=q.discount_minor > 0,
            total=format_minor(q.total_minor, q.currency, exp),
            exchange_rate=f"{q.exchange_rate.normalize():f}",
            expires_at=hold.expires_at,
            status=str(hold.status),
        )

    def pay(self, *, buyer_id: str, hold_id: str, payment_choice: str):
        choice = "decline" if payment_choice == "decline" else "approve"
        return self._coordinator(buyer_id).pay(PaymentRequest(hold_id=str(hold_id), payment_choice=choice))

    def cancel(self, *, buyer_id: str, hold_id: str):
        return self._coordinator(buyer_id).cancel(str(hold_id))

    def quick_buy(self, *, buyer_id: str, event_id: str, currency: str | None):
        """catalog-008: one ticket, buyer's saved currency, standard purchase path."""
        return self._coordinator(buyer_id).purchase(
            PurchaseRequest(event_id=str(event_id), quantity=1, currency=currency or "USD")
        )


class OrdersAdapter:
    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    def list_for_buyer(self, *, buyer_id: str):
        with unit_of_work(self._db) as tx:
            return OrderHistoryService(repository=PostgresOrderReader(tx)).list_for_buyer(buyer_id=buyer_id)

    def get_for_buyer(self, *, buyer_id: str, order_id: str):
        with unit_of_work(self._db) as tx:
            return OrderHistoryService(repository=PostgresOrderReader(tx)).get_for_buyer(
                buyer_id=buyer_id, order_id=order_id
            )


class AdminAdapter:
    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    def _call(self, fn):
        try:
            with unit_of_work(self._db) as tx:
                return fn(AdminService(repository=PostgresAdminRepository(tx)))
        except NotAuthorized as exc:
            raise ServiceError("forbidden", "Administrators only.", 403) from exc
        except RateValidationError as exc:
            raise ServiceError("invalid-rate", str(exc), 400) from exc

    def list_rates(self, *, actor: Principal | None):
        return self._call(lambda s: s.list_rates(actor))

    def set_rate(self, *, actor: Principal | None, currency: str, rate: str):
        return self._call(lambda s: s.set_rate(actor, currency=currency, rate=rate))

    def audit_page(self, *, actor: Principal | None, before_id: str | None = None):
        return self._call(lambda s: s.audit_page(actor, before_id=before_id))


def build_services(database: PostgresDatabase, *, environment: str) -> WebServices:
    session_policy = SessionPolicy.from_values(dict(os.environ), environment=environment)
    identity = IdentityAdapter(database, session_policy)
    catalog = CatalogAdapter(database)
    orders = OrdersAdapter(database)
    admin = AdminAdapter(database)
    try:
        pricing_policy = temporary_local_policy()
        pricing_policy.validate_for_environment(environment)
    except PricingUnavailable:
        # Fail closed: outside local/dev/test there is no approved price policy,
        # so browsing works but nothing can be priced or bought.
        return WebServices(
            identity=identity,
            catalog=catalog,
            pricing=unavailable_service(),
            checkout=unavailable_service(),
            purchase=unavailable_service(),
            orders=orders,
            admin=admin,
        )
    checkout = CheckoutAdapter(database, pricing_policy, PurchasePolicy())
    return WebServices(
        identity=identity,
        catalog=catalog,
        pricing=PricingAdapter(database, pricing_policy),
        checkout=checkout,
        purchase=checkout,
        orders=orders,
        admin=admin,
    )


def _sentence(text: str) -> str:
    text = text.strip()
    return (text[:1].upper() + text[1:] + ("" if text.endswith(".") else ".")) if text else text
