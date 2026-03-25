"""Demonstration job used to validate the shared JobRunner lifecycle."""

from __future__ import annotations

from typing import Any

from app.jobs.context import RunContext


class PingJob:
    """Return a predictable payload or fail on purpose for testing."""

    def __init__(self, *, should_fail: bool = False):
        self._should_fail = should_fail

    def __call__(self, context: RunContext) -> dict[str, Any]:
        if self._should_fail:
            raise RuntimeError("Demo ping job failed on purpose.")

        return {
            "message": "pong",
            "module_name": context.module_name,
            "job_name": context.job_name,
            "trigger_source": context.trigger_source,
            "mode": context.mode,
            "account_id": str(context.account_id) if context.account_id else None,
            "correlation_id": context.correlation_id,
        }


def build_ping_job(*, should_fail: bool = False) -> PingJob:
    """Build the demonstration ping job with optional failure mode."""
    return PingJob(should_fail=should_fail)
