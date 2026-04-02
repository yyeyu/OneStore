"""Temporary platform probe actions used in smoke checks."""

from __future__ import annotations

from hashlib import sha256

from app.actions.base import ActionResult, BaseAction
from app.actions.executor import ActionExecutor


class ProbeDispatchAction(BaseAction):
    """Temporary outward action used to validate the action runtime."""

    action_name = "probe_dispatch"
    module_name = "system_core"

    def __init__(
        self,
        *,
        target: str,
        message: str,
        account_id: int | None = None,
        should_fail: bool = False,
    ):
        super().__init__(account_id=account_id)
        self._target = target
        self._message = message
        self._should_fail = should_fail

    def run(self) -> dict[str, object]:
        if self._should_fail:
            raise RuntimeError("Probe action failed on purpose.")
        receipt_hash = sha256(f"{self._target}|{self._message}".encode("utf-8")).hexdigest()[:12]
        return {
            "delivery_state": "probe_dispatched",
            "probe_receipt": f"probe-{receipt_hash}",
            "target": self._target,
            "message": self._message,
        }


def execute_probe_action(
    *,
    target: str,
    message: str,
    account_id: int | None = None,
    run_id: int | None = None,
    should_fail: bool = False,
    executor: ActionExecutor | None = None,
) -> ActionResult:
    """Execute the temporary probe action through the shared executor."""
    action = ProbeDispatchAction(
        target=target,
        message=message,
        account_id=account_id,
        should_fail=should_fail,
    )
    active_executor = executor or ActionExecutor()
    return active_executor.execute(action=action, run_id=run_id)
