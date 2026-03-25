"""Demonstration actions for Module 0."""

from __future__ import annotations

from hashlib import sha256
from typing import Any
from uuid import UUID

from app.actions.base import BaseAction, ActionResult
from app.actions.executor import ActionExecutor
from app.jobs.context import RunMode


class DemoDispatchAction(BaseAction):
    """Mock outward action that never talks to a real external system."""

    module_name = "module0"
    action_name = "demo_dispatch"

    def __init__(
        self,
        *,
        target: str,
        message: str,
        account_id: UUID | None = None,
        should_fail: bool = False,
    ):
        super().__init__(account_id=account_id)
        self._target = target
        self._message = message
        self._should_fail = should_fail

    def build_request_payload(self) -> dict[str, Any]:
        return {
            "target": self._target,
            "message": self._message,
        }

    def build_idempotency_key(self) -> str:
        seed = f"{self.account_id or 'global'}|{self._target}|{self._message}"
        return sha256(seed.encode("utf-8")).hexdigest()

    def run_dry(self) -> dict[str, Any]:
        return {
            "dry_run": True,
            "mock_effect_applied": False,
            "preview": f"Would dispatch demo payload to {self._target}.",
            "target": self._target,
            "message": self._message,
        }

    def run_live(self) -> dict[str, Any]:
        if self._should_fail:
            raise RuntimeError("Demo action failed on purpose.")

        receipt_hash = sha256(
            f"{self._target}|{self._message}".encode("utf-8")
        ).hexdigest()[:12]
        return {
            "dry_run": False,
            "mock_effect_applied": True,
            "delivery_state": "mock_dispatched",
            "mock_receipt": f"demo-{receipt_hash}",
            "target": self._target,
            "message": self._message,
        }


def execute_demo_action(
    *,
    target: str,
    message: str,
    mode: RunMode,
    account_id: UUID | None = None,
    run_id: UUID | None = None,
    correlation_id: str | None = None,
    should_fail: bool = False,
    executor: ActionExecutor | None = None,
) -> ActionResult:
    """Execute the demonstration action through the shared Action executor."""
    action = DemoDispatchAction(
        target=target,
        message=message,
        account_id=account_id,
        should_fail=should_fail,
    )
    active_executor = executor or ActionExecutor()
    return active_executor.execute(
        action=action,
        mode=mode,
        run_id=run_id,
        correlation_id=correlation_id,
    )
