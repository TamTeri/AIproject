from __future__ import annotations

from dataclasses import dataclass

from app.web import create_web_app


@dataclass
class CatalogFake:
    events: list[dict]

    def list_events(self, *, query: str | None = None):
        return {"events": self.events, "query": query, "no_match": bool(query)}

    def get_event(self, *, event_id: str):
        return next((event for event in self.events if event["id"] == event_id), None)


class IdentityFake:
    def register(self, **kwargs):
        return {"account": {"id": "buyer-1", "name": kwargs["name"], "email": kwargs["email"]}}

    def authenticate(self, **kwargs):
        return {"account": {"id": "buyer-1", "name": "Buyer", "email": kwargs["email"]}}


class PricingFake:
    def quote(self, **kwargs):
        return {"snapshot_version": "QuoteV1", **kwargs, "total": "10.00"}


class CheckoutFake:
    def start(self, **kwargs):
        return {"hold_id": "hold-1", "event_id": kwargs["event_id"], "quantity": kwargs["quantity"]}

    def pay(self, **kwargs):
        return {"order_id": "order-1"}

    def cancel(self, **kwargs):
        return {"hold_id": kwargs["hold_id"], "status": "cancelled"}


class PurchaseFake:
    def quick_buy(self, **kwargs):
        return {"order_id": "order-1"}


class OrdersFake:
    def list_for_buyer(self, **kwargs):
        return []

    def get_for_buyer(self, **kwargs):
        return None


@dataclass
class ServicesFake:
    catalog: CatalogFake
    identity: IdentityFake = IdentityFake()
    pricing: PricingFake = PricingFake()
    checkout: CheckoutFake = CheckoutFake()
    purchase: PurchaseFake = PurchaseFake()
    orders: OrdersFake = OrdersFake()


def test_catalog_search_escapes_query_and_event_detail_has_one_explicit_quick_buy_button():
    services = ServicesFake(
        catalog=CatalogFake(
            events=[
                {
                    "id": "event-1",
                    "artist": "A & B",
                    "venue": "Main Hall",
                    "starts_at": "2026-11-01T20:00:00Z",
                    "available": 12,
                }
            ]
        )
    )
    app = create_web_app(services=services, config={"TESTING": True, "SECRET_KEY": "test"})
    client = app.test_client()

    search = client.get("/events?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E")
    assert search.status_code == 200
    body = search.get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<script>alert(1)</script>" not in body

    detail = client.get("/events/event-1")
    assert detail.status_code == 200
    detail_body = detail.get_data(as_text=True)
    assert detail_body.count(">Quick Buy<") == 1
    assert "ondblclick" not in detail_body
