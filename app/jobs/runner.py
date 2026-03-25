"""Shared lifecycle runner for manual and scheduled jobs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ModuleRun
from app.db.session import get_session_factory
from app.jobs.context import RunContext

JobCallable = Callable[[RunContext], dict[str, Any] | None]


class JobRunResult(BaseModel):
    """Structured job execution result."""

    run_id: int
    module_id: int
    module_name: str
    job_name: str
    trigger_source: str
    account_id: int | None
    status: str
    error_message: str | None = None
    payload: dict[str, Any] | None = None


class JobRunner:
    """Execute one job and journal it in module_runs."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()
        self._logger = logging.getLogger(__name__)

    def run(
        self,
        *,
        context: RunContext,
        module_id: int,
        job: JobCallable,
    ) -> JobRunResult:
        """Run a job and persist running/success/error lifecycle."""
        started_at = datetime.now(timezone.utc)
        with self._session_factory() as session:
            run_record = ModuleRun(
                account_id=context.account_id,
                module_id=module_id,
                job_name=context.job_name,
                trigger_source=context.trigger_source,
                status="running",
                started_at=started_at,
            )
            session.add(run_record)
            session.commit()
            session.refresh(run_record)

            self._logger.info(
                "Job run started",
                extra=self._log_fields(
                    run_id=run_record.id,
                    module_id=module_id,
                    context=context,
                    status="running",
                ),
            )

            try:
                payload = job(context) or {}
            except Exception as exc:
                run_record.status = "error"
                run_record.error_message = str(exc)
                run_record.finished_at = datetime.now(timezone.utc)
                session.add(run_record)
                session.commit()
                session.refresh(run_record)

                self._logger.exception(
                    "Job run failed",
                    extra=self._log_fields(
                        run_id=run_record.id,
                        module_id=module_id,
                        context=context,
                        status="error",
                    ),
                )
                return JobRunResult(
                    run_id=run_record.id,
                    module_id=module_id,
                    module_name=context.module_name,
                    job_name=context.job_name,
                    trigger_source=context.trigger_source,
                    account_id=context.account_id,
                    status=run_record.status,
                    error_message=run_record.error_message,
                    payload=None,
                )

            run_record.status = "success"
            run_record.finished_at = datetime.now(timezone.utc)
            session.add(run_record)
            session.commit()
            session.refresh(run_record)

            self._logger.info(
                "Job run finished successfully",
                extra=self._log_fields(
                    run_id=run_record.id,
                    module_id=module_id,
                    context=context,
                    status="success",
                ),
            )
            return JobRunResult(
                run_id=run_record.id,
                module_id=module_id,
                module_name=context.module_name,
                job_name=context.job_name,
                trigger_source=context.trigger_source,
                account_id=context.account_id,
                status=run_record.status,
                error_message=run_record.error_message,
                payload=payload,
            )

    @staticmethod
    def _log_fields(
        *,
        run_id: int,
        module_id: int,
        context: RunContext,
        status: str,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "module_id": module_id,
            "module_name": context.module_name,
            "job_name": context.job_name,
            "trigger_source": context.trigger_source,
            "account_id": context.account_id,
            "status": status,
        }
