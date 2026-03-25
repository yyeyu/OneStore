"""Base interfaces and result models for the Action layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

ActionStatus = Literal["success", "error"]


class ActionResult(BaseModel):
    """Outcome returned by the ActionExecutor."""

    action_log_id: int
    action_name: str
    account_id: int | None
    run_id: int | None
    status: ActionStatus
    error_message: str | None = None
    output: dict[str, Any] | None = None


class BaseAction(ABC):
    """Base outward action."""

    action_name: str
    module_name: str = "module0"

    def __init__(self, *, account_id: int | None = None):
        self.account_id = account_id

    @abstractmethod
    def run(self) -> dict[str, Any] | None:
        """Execute the action side effect."""
