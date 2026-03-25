"""Helpers for programmatic Alembic execution."""

from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config

from app.core.settings import Settings, get_settings


def make_alembic_config(settings: Settings | None = None) -> Config:
    """Build an Alembic config object for the current environment."""
    current_settings = settings or get_settings()
    project_root = current_settings.project_root
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    config.set_main_option("sqlalchemy.url", current_settings.database_url)
    return config


def upgrade_database(revision: str = "head", settings: Settings | None = None) -> None:
    """Apply Alembic migrations up to the requested revision."""
    logger = logging.getLogger(__name__)
    logger.info(
        "Database migration started",
        extra={
            "module_name": "system",
            "status": "started",
            "revision": revision,
        },
    )
    config = make_alembic_config(settings=settings)
    try:
        command.upgrade(config, revision)
    except Exception:
        logger.exception(
            "Database migration failed",
            extra={
                "module_name": "system",
                "status": "error",
                "revision": revision,
            },
        )
        raise

    logger.info(
        "Database migration completed",
        extra={
            "module_name": "system",
            "status": "ok",
            "revision": revision,
        },
    )
