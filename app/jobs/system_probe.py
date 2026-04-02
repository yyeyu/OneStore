"""Temporary platform probe job used to validate the shared JobRunner lifecycle."""

from __future__ import annotations

from typing import Any

from app.jobs.context import RunContext


class SystemProbeJob:
    """Return a predictable payload or fail on purpose for runtime checks."""

    def __init__(self, *, should_fail: bool = False):
        self._should_fail = should_fail

    def __call__(self, context: RunContext) -> dict[str, Any]:
        if self._should_fail:
            raise RuntimeError("System probe job failed on purpose.")

        return {
            "message": "system_probe_ok",
            "module_name": context.module_name,
            "job_name": context.job_name,
            "trigger_source": context.trigger_source,
            "account_id": context.account_id,
        }


def build_system_probe_job(*, should_fail: bool = False) -> SystemProbeJob:
    """Build the temporary system probe job with optional failure mode."""
    return SystemProbeJob(should_fail=should_fail)
