"""EventHub main program: builds the Flask app and plugs in every feature.

Each feature (identity, catalog, pricing, inventory, purchase, orders, audit,
admin) lives in its own package and can be unit-tested on its own with fakes.
This factory is the single place that connects them to PostgreSQL and the web.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any

from flask import Flask

from app.config.settings import ConfigurationError, Settings

_LOCAL_ENVIRONMENTS = {"local", "development", "test"}


def create_app(test_config: Mapping[str, Any] | None = None) -> Flask:
    settings = Settings.from_values(test_config)

    app = Flask(__name__)
    app.config.from_mapping(
        ENVIRONMENT=settings.environment,
        SQLALCHEMY_DATABASE_URI=settings.database_url,
        EVENTHUB_SEED_FILE=str(settings.seed_file),
        EVENTHUB_RESET_ENABLED=settings.reset_enabled,
        SECRET_KEY=_secret_key(settings.environment, test_config),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.environment not in _LOCAL_ENVIRONMENTS,
    )
    if test_config:
        app.config.update(test_config)
        app.config["SQLALCHEMY_DATABASE_URI"] = settings.database_url

    # Imported here so unit tests of single features never need the web stack.
    from app.db.transaction import PostgresDatabase
    from app.web import register_web
    from app.wiring import build_services

    database = PostgresDatabase(settings.database_url)
    app.extensions["eventhub_database"] = database
    register_web(app, build_services(database, environment=settings.environment))

    @app.get("/healthz")
    def healthz() -> tuple[dict[str, str], int]:
        return {"service": "eventhub", "status": "ok"}, 200

    return app


def _secret_key(environment: str, overrides: Mapping[str, Any] | None) -> str:
    import os

    supplied = (overrides or {}).get("SECRET_KEY") or os.environ.get("EVENTHUB_SECRET_KEY")
    if supplied:
        return str(supplied)
    if environment in _LOCAL_ENVIRONMENTS:
        # Local/demo only: sessions reset when the server restarts.
        return secrets.token_hex(32)
    raise ConfigurationError("EVENTHUB_SECRET_KEY is required outside local/development/test")


__all__ = ["create_app"]
