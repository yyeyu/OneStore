"""Shared execution context for jobs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

TriggerSource = Literal["manual", "scheduler", "event", "retry"]
RunStatus = Literal["running", "success", "error"]


class RunContext(BaseModel):
    """Immutable input context for one job execution."""

    model_config = ConfigDict(frozen=True)

    module_name: str
    job_name: str
    trigger_source: TriggerSource
    account_id: int | None = None
