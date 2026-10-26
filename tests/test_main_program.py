"""The main program includes every feature (Part 4 requirement).

Builds the real app without touching the database (engines connect lazily).
"""

from __future__ import annotations

import importlib

import pytest

from app import create_app

FEATURES = ["identity", "catalog", "pricing", "inventory", "purchase", "orders", "audit", "admin"]


@pytest.fixture
def app():
    return create_app(
        {"TESTING": True, "SECRET_KEY": "x", "DATABASE_URL": "postgresql+psycopg://u:p@localhost:1/none"}
    )


@pytest.mark.parametrize("feature", FEATURES)
def test_each_feature_is_a_standalone_importable_package(feature):
    module = importlib.import_module(f"app.{feature}")
    assert module.__doc__


def test_app_routes_cover_every_feature(app):
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    expected = {
        "/register",
        "/login",
        "/logout",
        "/account",  # identity
        "/events",
        "/events/<event_id>",  # catalog
        "/events/<event_id>/checkout",
        "/checkout/<hold_id>",
        "/checkout/<hold_id>/pay",
        "/checkout/<hold_id>/cancel",
        "/events/<event_id>/quick-buy",  # purchase + inventory + pricing
        "/orders",
        "/orders/<order_id>",  # orders
        "/admin/rates",
        "/admin/audit",  # admin + audit
        "/healthz",
    }
    assert expected <= rules


def test_every_service_port_is_wired_to_a_real_adapter(app):
    services = app.extensions["eventhub_web_services"]
    for name in ("identity", "catalog", "pricing", "checkout", "purchase", "orders", "admin"):
        port = getattr(services, name)
        assert type(port).__module__ == "app.wiring", name


def test_production_requires_a_secret_key(monkeypatch):
    from app.config.settings import ConfigurationError

    monkeypatch.delenv("EVENTHUB_SECRET_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        create_app({"DATABASE_URL": "postgresql://u:p@localhost/x", "EVENTHUB_ENVIRONMENT": "production"})
