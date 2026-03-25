"""Shared execution context for all jobs."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

RunMode = Literal["dry_run", "live"]
TriggerSource = Literal["manual", "scheduler", "retry"]
RunStatus = Literal["started", "success", "error", "locked"]


class RunContext(BaseModel):
    """Immutable context passed into every job execution."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID = Field(default_factory=uuid4)
    correlation_id: str = Field(default_factory=lambda: uuid4().hex)
    module_name: str
    job_name: str
    trigger_source: TriggerSource
    mode: RunMode
    account_id: UUID | None = None
    logical_scope: str = "default"
