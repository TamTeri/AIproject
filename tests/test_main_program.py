"""The main program includes every feature (Part 4 requirement; system-003, system-004, system-005, system-012).

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


@pytest.mark.requirement("system-017")
def test_healthz_reports_version_and_alembic_head_unknown_when_db_down(app, monkeypatch):
    import app as app_module

    def unreachable(_url):
        raise OSError("db down")

    monkeypatch.setattr(app_module, "_probe_engine", unreachable)
    body = app.test_client().get("/healthz").get_json()
    assert body["status"] == "ok"
    assert body["version"] not in ("", None)
    assert body["alembic_head"] == "unknown"  # port 1 is unreachable


@pytest.mark.requirement("system-017")
def test_healthz_reads_alembic_head_when_db_is_up(app, monkeypatch):
    from contextlib import contextmanager

    import app as app_module

    class Conn:
        def execute(self, _):
            class R:
                def scalar_one(self):
                    return "0006_call5_rate_windows"

            return R()

    class Engine:
        @contextmanager
        def connect(self):
            yield Conn()

    monkeypatch.setattr(app_module, "_probe_engine", lambda _url: Engine())
    body = app.test_client().get("/healthz").get_json()
    assert body["alembic_head"] == "0006_call5_rate_windows"


@pytest.mark.requirement("system-017")
def test_release_version_is_1_3_0():
    import tomllib
    from pathlib import Path

    data = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert data["project"]["version"] == "1.3.0"


def test_production_requires_a_secret_key(monkeypatch):
    from app.config.settings import ConfigurationError

    monkeypatch.delenv("EVENTHUB_SECRET_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        create_app({"DATABASE_URL": "postgresql://u:p@localhost/x", "EVENTHUB_ENVIRONMENT": "production"})
