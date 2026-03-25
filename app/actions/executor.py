"""Shared executor for outward actions with audit logging."""

from __future__ import annotations

from collections.abc import Callable
import logging

from sqlalchemy.orm import Session, sessionmaker

from app.actions.base import ActionResult, BaseAction
from app.db.models import ActionLog
from app.db.session import get_session_factory


class ActionExecutor:
    """Execute actions and persist success/error audit logs."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()
        self._logger = logging.getLogger(__name__)

    def execute(
        self,
        *,
        action: BaseAction,
        run_id: int | None = None,
    ) -> ActionResult:
        """Execute one action and write one audit row."""
        with self._session_factory() as session:
            try:
                output = action.run() or {}
            except Exception as exc:
                action_log = ActionLog(
                    account_id=action.account_id,
                    run_id=run_id,
                    action_name=action.action_name,
                    status="error",
                    error_message=str(exc),
                )
                session.add(action_log)
                session.commit()
                session.refresh(action_log)

                self._logger.exception(
                    "Action execution failed",
                    extra={
                        "action_name": action.action_name,
                        "account_id": action.account_id,
                        "run_id": run_id,
                        "status": "error",
                    },
                )
                return ActionResult(
                    action_log_id=action_log.id,
                    action_name=action.action_name,
                    account_id=action.account_id,
                    run_id=run_id,
                    status="error",
                    error_message=str(exc),
                    output=None,
                )

            action_log = ActionLog(
                account_id=action.account_id,
                run_id=run_id,
                action_name=action.action_name,
                status="success",
                error_message=None,
            )
            session.add(action_log)
            session.commit()
            session.refresh(action_log)

            self._logger.info(
                "Action execution finished",
                extra={
                    "action_name": action.action_name,
                    "account_id": action.account_id,
                    "run_id": run_id,
                    "status": "success",
                },
            )
            return ActionResult(
                action_log_id=action_log.id,
                action_name=action.action_name,
                account_id=action.account_id,
                run_id=run_id,
                status="success",
                error_message=None,
                output=output,
            )
