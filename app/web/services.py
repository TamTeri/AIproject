from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ServiceError(Exception):
    """Safe, stable failure raised by a downstream service port."""

    def __init__(self, code: str, message: str, status_code: int = 400, fields: dict[str, str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.fields = fields or {}


class IdentityPort(Protocol):
    def register(self, *, name: str, email: str, password: str) -> Any: ...
    def authenticate(self, *, email: str, password: str) -> Any: ...
    def start_session(self, *, account_id: str) -> str: ...
    def resolve_session(self, *, token: str | None) -> Any: ...
    def end_session(self, *, token: str | None) -> None: ...
    def set_preferred_currency(self, *, account_id: str, currency: str) -> None: ...


class CatalogPort(Protocol):
    def list_events(self, *, query: str | None = None) -> Any: ...
    def get_event(self, *, event_id: str) -> Any: ...


class PricingPort(Protocol):
    def currencies(self) -> list[str]: ...
    def base_price_display(self, *, base_price_minor: int) -> str: ...


class CheckoutPort(Protocol):
    def start(self, *, buyer_id: str, event_id: str, quantity: Any, currency: Any) -> Any: ...
    def review(self, *, buyer_id: str, hold_id: str) -> Any: ...
    def pay(self, *, buyer_id: str, hold_id: str, payment_choice: str) -> Any: ...
    def cancel(self, *, buyer_id: str, hold_id: str) -> Any: ...


class PurchasePort(Protocol):
    def quick_buy(self, *, buyer_id: str, event_id: str, currency: str | None) -> Any: ...


class OrdersPort(Protocol):
    def list_for_buyer(self, *, buyer_id: str) -> Any: ...
    def get_for_buyer(self, *, buyer_id: str, order_id: str) -> Any: ...


class AdminPort(Protocol):
    def list_rates(self, *, actor: Any) -> Any: ...
    def set_rate(self, *, actor: Any, currency: str, rate: str) -> Any: ...
    def audit_page(self, *, actor: Any, before_id: str | None = None) -> Any: ...


@dataclass(frozen=True)
class WebServices:
    identity: IdentityPort
    catalog: CatalogPort
    pricing: PricingPort
    checkout: CheckoutPort
    purchase: PurchasePort
    orders: OrdersPort
    admin: AdminPort | Any = None


class _UnavailableService:
    def __getattr__(self, name: str):
        def unavailable(**_: Any):
            raise ServiceError(
                "service-unavailable",
                "This EventHub service is temporarily unavailable.",
                503,
            )

        return unavailable


def unavailable_service() -> Any:
    return _UnavailableService()


def default_services() -> WebServices:
    """Every port unavailable (503). Used when no wiring is supplied."""
    unavailable = _UnavailableService()
    return WebServices(
        identity=unavailable,
        catalog=unavailable,
        pricing=unavailable,
        checkout=unavailable,
        purchase=unavailable,
        orders=unavailable,
        admin=unavailable,
    )
