"""Logging helpers for the platform."""

from __future__ import annotations

import json
import logging
from typing import Any

_CONFIGURED = False

STABLE_LOG_FIELDS = (
    "run_id",
    "module_id",
    "module_name",
    "job_name",
    "action_name",
    "account_id",
    "status",
    "trigger_source",
)

STANDARD_LOG_RECORD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class StableContextFilter(logging.Filter):
    """Ensure stable structured fields always exist on log records."""

    def __init__(self, *, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = getattr(record, "service", self._service)
        record.environment = getattr(record, "environment", self._environment)
        for field in STABLE_LOG_FIELDS:
            if not hasattr(record, field):
                setattr(record, field, None)
        return True


class TextLogFormatter(logging.Formatter):
    """Human-readable formatter with stable investigation fields."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        base = (
            f"{timestamp} | {record.levelname} | {record.name} | {record.getMessage()}"
        )
        context = " ".join(
            f"{field}={self._normalize(getattr(record, field, None))}"
            for field in STABLE_LOG_FIELDS
        )
        extras = self._collect_extra_fields(record)
        if extras:
            extras_text = (
                f" | extras={json.dumps(extras, ensure_ascii=True, sort_keys=True, default=str)}"
            )
        else:
            extras_text = ""
        if record.exc_info:
            exception_text = f" | exception={self.formatException(record.exc_info)}"
        else:
            exception_text = ""
        return (
            f"{base} | service={self._normalize(record.service)} "
            f"environment={self._normalize(record.environment)} {context}"
            f"{extras_text}"
            f"{exception_text}"
        )

    @staticmethod
    def _normalize(value: Any) -> str:
        return "null" if value is None else str(value)

    @staticmethod
    def _collect_extra_fields(record: logging.LogRecord) -> dict[str, Any]:
        return {
            key: value
            for key, value in record.__dict__.items()
            if key not in STANDARD_LOG_RECORD_FIELDS
            and key not in STABLE_LOG_FIELDS
            and key not in {"service", "environment"}
        }


class JsonLogFormatter(logging.Formatter):
    """Structured JSON formatter suitable for local parsing and log shipping."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": record.service,
            "environment": record.environment,
        }
        for field in STABLE_LOG_FIELDS:
            payload[field] = getattr(record, field, None)
        payload.update(TextLogFormatter._collect_extra_fields(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(
    level: str = "INFO",
    log_format: str = "text",
    *,
    service: str = "Avito AI Assistant",
    environment: str = "local",
) -> None:
    """Configure process-wide logging once and keep the level adjustable."""
    global _CONFIGURED

    normalized_level = level.upper()
    normalized_format = log_format.lower()
    root_logger = logging.getLogger()
    formatter: logging.Formatter
    if normalized_format == "json":
        formatter = JsonLogFormatter()
    else:
        formatter = TextLogFormatter()

    if not _CONFIGURED:
        handler = logging.StreamHandler()
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        _CONFIGURED = True

    root_logger.setLevel(normalized_level)
    for handler in root_logger.handlers:
        handler.setLevel(normalized_level)
        handler.setFormatter(formatter)
        handler.filters.clear()
        handler.addFilter(
            StableContextFilter(
                service=service,
                environment=environment,
            )
        )
