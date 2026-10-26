from __future__ import annotations

from pathlib import Path

from alembic.config import Config


def alembic_config(*, database_url: str, migrations_path: Path | None = None) -> Config:
    """Build an Alembic config without opening a database connection."""
    root = Path(__file__).resolve().parents[2]
    script_location = migrations_path or root / "migrations"

    config = Config()
    config.set_main_option("script_location", str(script_location))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config
