from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text


SEED_POLICY_STATUS = "[TEMPORARY_MVP_DEFAULT] [PROVISIONAL_LOCAL_ONLY]"


class SeedFixtureError(ValueError):
    """Raised when the deterministic local/demo seed is malformed."""


def load_seed_fixture(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SeedFixtureError(f"invalid database seed fixture: {path}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise SeedFixtureError("database seed schema_version must be 1")
    if payload.get("policy_status") != SEED_POLICY_STATUS:
        raise SeedFixtureError(
            "database seed must be labeled [TEMPORARY_MVP_DEFAULT] [PROVISIONAL_LOCAL_ONLY]"
        )
    for key in ("currencies", "exchange_rates", "config", "events"):
        if not isinstance(payload.get(key), list) or not payload[key]:
            raise SeedFixtureError(f"database seed must contain a non-empty {key} list")

    fixed_timestamp = payload.get("seeded_at")
    if not isinstance(fixed_timestamp, str):
        raise SeedFixtureError("database seed must contain a fixed seeded_at timestamp")
    _parse_timestamp(fixed_timestamp)
    return payload


def seed_connection(connection: Connection, fixture: dict[str, Any]) -> None:
    seeded_at = fixture["seeded_at"]

    connection.execute(
        text(
            """
            INSERT INTO eventhub_bootstrap (key, value)
            VALUES (:key, CAST(:value AS JSONB))
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """
        ),
        {
            "key": "catalog-seed",
            "value": json.dumps({"seeded_at": seeded_at, "policy_status": SEED_POLICY_STATUS}, sort_keys=True),
        },
    )

    for currency in fixture["currencies"]:
        _require_keys(currency, "code", "minor_unit", "enabled")
        connection.execute(
            text(
                """
                INSERT INTO currencies (code, minor_unit, enabled, created_at)
                VALUES (:code, :minor_unit, :enabled, :created_at)
                ON CONFLICT (code) DO UPDATE SET
                    minor_unit = EXCLUDED.minor_unit,
                    enabled = EXCLUDED.enabled
                """
            ),
            {
                "code": currency["code"],
                "minor_unit": currency["minor_unit"],
                "enabled": currency["enabled"],
                "created_at": seeded_at,
            },
        )

    for rate in fixture["exchange_rates"]:
        _require_keys(rate, "currency_code", "rate")
        connection.execute(
            text(
                """
                INSERT INTO exchange_rates (currency_code, rate, updated_at)
                VALUES (:currency_code, :rate, :updated_at)
                ON CONFLICT (currency_code) DO UPDATE SET
                    rate = EXCLUDED.rate,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "currency_code": rate["currency_code"],
                "rate": rate["rate"],
                "updated_at": seeded_at,
            },
        )

    for config in fixture["config"]:
        _require_keys(config, "config_key", "value_json", "policy_status")
        if config["policy_status"] != SEED_POLICY_STATUS:
            raise SeedFixtureError(
                f"config {config['config_key']} is not labeled temporary local-only"
            )
        connection.execute(
            text(
                """
                INSERT INTO app_config
                    (config_key, value_json, policy_status, updated_at)
                VALUES
                    (:config_key, CAST(:value_json AS JSONB), :policy_status, :updated_at)
                ON CONFLICT (config_key) DO UPDATE SET
                    value_json = EXCLUDED.value_json,
                    policy_status = EXCLUDED.policy_status,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "config_key": config["config_key"],
                "value_json": json.dumps(config["value_json"], sort_keys=True),
                "policy_status": config["policy_status"],
                "updated_at": seeded_at,
            },
        )

    for event in fixture["events"]:
        _require_keys(
            event,
            "catalog_key",
            "title",
            "artist",
            "venue",
            "starts_at",
            "host_type",
            "base_price_minor",
            "capacity",
        )
        _parse_timestamp(event["starts_at"])
        connection.execute(
            text(
                """
                INSERT INTO events
                    (catalog_key, title, artist, venue, starts_at, host_type,
                     base_price_minor, capacity, created_at)
                VALUES
                    (:catalog_key, :title, :artist, :venue, :starts_at, :host_type,
                     :base_price_minor, :capacity, :created_at)
                ON CONFLICT (catalog_key) DO UPDATE SET
                    title = EXCLUDED.title,
                    artist = EXCLUDED.artist,
                    venue = EXCLUDED.venue,
                    starts_at = EXCLUDED.starts_at,
                    host_type = EXCLUDED.host_type,
                    base_price_minor = EXCLUDED.base_price_minor,
                    capacity = EXCLUDED.capacity
                """
            ),
            {
                "catalog_key": event["catalog_key"],
                "title": event["title"],
                "artist": event["artist"],
                "venue": event["venue"],
                "starts_at": event["starts_at"],
                "host_type": event["host_type"],
                "base_price_minor": event["base_price_minor"],
                "capacity": event["capacity"],
                "created_at": seeded_at,
            },
        )


def _require_keys(value: dict[str, Any], *keys: str) -> None:
    if not isinstance(value, dict) or any(key not in value for key in keys):
        raise SeedFixtureError(f"seed row must contain keys: {', '.join(keys)}")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SeedFixtureError(f"invalid seed timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise SeedFixtureError(f"seed timestamp must include a timezone: {value}")
    return parsed
