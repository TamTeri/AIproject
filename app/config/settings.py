from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigurationError(RuntimeError):
    """Raised when required bootstrap configuration is absent or invalid."""


@dataclass(frozen=True)
class Settings:
    """Validated runtime settings; unresolved product policy is not represented here."""

    environment: str
    database_url: str
    seed_file: Path
    reset_enabled: bool

    @classmethod
    def from_values(cls, overrides: Mapping[str, object] | None = None) -> Settings:
        values: dict[str, object] = dict(os.environ)
        if overrides:
            values.update(overrides)

        database_url = _string_value(values.get("DATABASE_URL") or values.get("EVENTHUB_DATABASE_URL"))
        if not database_url:
            raise ConfigurationError("DATABASE_URL is required; EventHub does not provide a SQLite fallback")
        _validate_postgresql_url(database_url)

        environment = _string_value(values.get("EVENTHUB_ENVIRONMENT")) or "development"
        seed_file = Path(_string_value(values.get("EVENTHUB_SEED_FILE")) or "seed/bootstrap.json")
        reset_enabled = _boolean_value(values.get("EVENTHUB_RESET_ENABLED"), default=False)

        return cls(
            environment=environment,
            database_url=database_url,
            seed_file=seed_file,
            reset_enabled=reset_enabled,
        )


def _string_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _boolean_value(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError("EVENTHUB_RESET_ENABLED must be one of: 0, 1, false, true, no, yes, off, on")


def _validate_postgresql_url(database_url: str) -> None:
    scheme = urlparse(database_url).scheme.lower()
    if scheme not in {"postgresql", "postgresql+psycopg"}:
        raise ConfigurationError("DATABASE_URL must use PostgreSQL (postgresql:// or postgresql+psycopg://)")
