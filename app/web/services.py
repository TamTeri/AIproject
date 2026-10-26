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


class CatalogPort(Protocol):
    def list_events(self, *, query: str | None = None) -> Any: ...
    def get_event(self, *, event_id: str) -> Any: ...


class PricingPort(Protocol):
    def quote(self, *, buyer_id: str, event_id: str, quantity: int, currency: str) -> Any: ...


class CheckoutPort(Protocol):
    def start(self, *, buyer_id: str, event_id: str, quantity: int, currency: str) -> Any: ...
    def pay(self, *, buyer_id: str, hold_id: str, payment_choice: str) -> Any: ...
    def cancel(self, *, buyer_id: str, hold_id: str) -> Any: ...


class PurchasePort(Protocol):
    def quick_buy(self, *, buyer_id: str, event_id: str) -> Any: ...


class OrdersPort(Protocol):
    def list_for_buyer(self, *, buyer_id: str) -> Any: ...
    def get_for_buyer(self, *, buyer_id: str, order_id: str) -> Any: ...


@dataclass(frozen=True)
class WebServices:
    identity: IdentityPort
    catalog: CatalogPort
    pricing: PricingPort
    checkout: CheckoutPort
    purchase: PurchasePort
    orders: OrdersPort


class _UnavailableService:
    def __getattr__(self, name: str):
        def unavailable(**_: Any):
            raise ServiceError(
                "service-unavailable",
                "This EventHub service is temporarily unavailable.",
                503,
            )

        return unavailable


def default_services() -> WebServices:
    """Return explicit local wiring until domain lanes provide their adapters."""
    unavailable = _UnavailableService()
    return WebServices(
        identity=unavailable,
        catalog=unavailable,
        pricing=unavailable,
        checkout=unavailable,
        purchase=unavailable,
        orders=unavailable,
    )
