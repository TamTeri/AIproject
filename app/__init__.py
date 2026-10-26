from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from app.config.settings import Settings


db = SQLAlchemy()


def create_app(test_config: Mapping[str, Any] | None = None) -> Flask:
    """Create the Flask application without selecting product policy defaults."""
    settings = Settings.from_values(test_config)

    app = Flask(__name__)
    app.config.from_mapping(
        ENVIRONMENT=settings.environment,
        SQLALCHEMY_DATABASE_URI=settings.database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        EVENTHUB_SEED_FILE=str(settings.seed_file),
        EVENTHUB_RESET_ENABLED=settings.reset_enabled,
    )
    if test_config:
        app.config.update(test_config)
        app.config["SQLALCHEMY_DATABASE_URI"] = settings.database_url

    db.init_app(app)

    @app.get("/healthz")
    def healthz() -> tuple[dict[str, str], int]:
        return {"service": "eventhub", "status": "ok"}, 200

    return app


__all__ = ["create_app", "db"]
