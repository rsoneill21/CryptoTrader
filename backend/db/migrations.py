"""Helpers to run Alembic migrations programmatically."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from db.database import DATABASE_URL


def _alembic_config() -> Config:
    """Build an Alembic `Config` preloaded with the project settings."""

    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    database_url = os.getenv("DATABASE_URL", DATABASE_URL)
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def run_migrations() -> None:
    """Upgrade the database schema to the latest revision."""

    config = _alembic_config()
    command.upgrade(config, "head")
