from __future__ import annotations

import json
import logging
from io import StringIO

from app.core.logging import configure_logging


def _capture_root_stream() -> StringIO:
    root_logger = logging.getLogger()
    assert root_logger.handlers
    stream = StringIO()
    root_logger.handlers[0].stream = stream
    return stream


def test_configure_logging_text_includes_stable_fields_and_extras() -> None:
    configure_logging(
        "INFO",
        "text",
        service="Avito AI Assistant",
        environment="test",
    )
    stream = _capture_root_stream()

    logging.getLogger("test.text").info(
        "hello text logs",
        extra={
            "module_name": "module0",
            "job_name": "ping",
            "run_id": "run-1",
            "correlation_id": "corr-1",
            "account_id": "acc-1",
            "status": "success",
            "custom_detail": "visible",
        },
    )

    output = stream.getvalue()
    assert "hello text logs" in output
    assert "service=Avito AI Assistant" in output
    assert "environment=test" in output
    assert "run_id=run-1" in output
    assert "correlation_id=corr-1" in output
    assert "module_name=module0" in output
    assert "job_name=ping" in output
    assert "account_id=acc-1" in output
    assert "status=success" in output
    assert '"custom_detail": "visible"' in output


def test_configure_logging_json_emits_structured_payload() -> None:
    configure_logging(
        "INFO",
        "json",
        service="Avito AI Assistant",
        environment="test-json",
    )
    stream = _capture_root_stream()

    logging.getLogger("test.json").warning(
        "hello json logs",
        extra={
            "module_name": "module0",
            "status": "warning",
            "registered_jobs": ["job:ping"],
        },
    )

    payload = json.loads(stream.getvalue())
    assert payload["message"] == "hello json logs"
    assert payload["service"] == "Avito AI Assistant"
    assert payload["environment"] == "test-json"
    assert payload["module_name"] == "module0"
    assert payload["status"] == "warning"
    assert payload["registered_jobs"] == ["job:ping"]
