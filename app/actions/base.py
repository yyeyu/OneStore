"""Base interfaces and result models for the Action layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.jobs.context import RunMode

ActionStatus = Literal["dry_run", "success", "error", "duplicate"]


class ActionResult(BaseModel):
    """Structured outcome returned by the shared Action executor."""

    action_log_id: str
    module_name: str
    action_name: str
    account_id: str | None
    run_id: str | None
    correlation_id: str
    mode: RunMode
    status: ActionStatus
    idempotency_key: str
    duplicate: bool
    request_payload: dict[str, Any] | None = None
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None


class BaseAction(ABC):
    """Unified interface for potentially risky outward actions."""

    module_name: str
    action_name: str

    def __init__(self, *, account_id: UUID | None = None):
        self.account_id = account_id

    @property
    def idempotency_scope(self) -> str:
        """Return the logical deduplication scope for the action."""
        return f"{self.module_name}:{self.action_name}"

    @abstractmethod
    def build_request_payload(self) -> dict[str, Any]:
        """Return the serializable request payload for audit logging."""

    @abstractmethod
    def build_idempotency_key(self) -> str:
        """Return a stable idempotency key for identical action requests."""

    def run_dry(self) -> dict[str, Any]:
        """Return a safe preview when the action runs in dry-run mode."""
        return {
            "dry_run": True,
            "message": f"Dry-run completed for {self.action_name}.",
            "external_effect_applied": False,
        }

    @abstractmethod
    def run_live(self) -> dict[str, Any]:
        """Execute the live branch of the action."""
