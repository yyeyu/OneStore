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
        service="OneStore",
        environment="test",
    )
    stream = _capture_root_stream()

    logging.getLogger("test.text").info(
        "hello text logs",
        extra={
            "module_name": "system_core",
            "job_name": "system-probe",
            "run_id": "run-1",
            "module_id": 1,
            "account_id": "acc-1",
            "status": "success",
            "custom_detail": "visible",
        },
    )

    output = stream.getvalue()
    assert "hello text logs" in output
    assert "service=OneStore" in output
    assert "environment=test" in output
    assert "run_id=run-1" in output
    assert "module_id=1" in output
    assert "module_name=system_core" in output
    assert "job_name=system-probe" in output
    assert "account_id=acc-1" in output
    assert "status=success" in output
    assert '"custom_detail": "visible"' in output


def test_configure_logging_json_emits_structured_payload() -> None:
    configure_logging(
        "INFO",
        "json",
        service="OneStore",
        environment="test-json",
    )
    stream = _capture_root_stream()

    logging.getLogger("test.json").warning(
        "hello json logs",
        extra={
            "module_name": "system_core",
            "status": "warning",
            "registered_jobs": ["job:system-probe"],
        },
    )

    payload = json.loads(stream.getvalue())
    assert payload["message"] == "hello json logs"
    assert payload["service"] == "OneStore"
    assert payload["environment"] == "test-json"
    assert payload["module_name"] == "system_core"
    assert payload["status"] == "warning"
    assert payload["registered_jobs"] == ["job:system-probe"]
