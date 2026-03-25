"""Shared diagnostics payloads for CLI and smoke workflows."""

from __future__ import annotations

from typing import Any

from app.core.settings import Settings, get_settings


def build_system_summary(settings: Settings | None = None) -> dict[str, Any]:
    """Return the stable system summary used by CLI and smoke checks."""
    active_settings = settings or get_settings()
    return {
        "status": "ok",
        "service": active_settings.app_name,
        "environment": active_settings.environment,
        "version": active_settings.version,
        "debug": active_settings.debug,
        "log_level": active_settings.log_level,
        "log_format": active_settings.log_format,
        "account_identifier": "account_id",
    }
