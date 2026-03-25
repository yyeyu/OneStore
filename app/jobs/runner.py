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
from app.jobs.context import RunContext, RunStatus
from app.jobs.locks import JobLockAcquisition, JobLockManager

JobCallable = Callable[[RunContext], dict[str, Any] | None]


class JobRunResult(BaseModel):
    """Structured outcome returned by the JobRunner."""

    run_id: str
    correlation_id: str
    module_name: str
    job_name: str
    trigger_source: str
    mode: str
    account_id: str | None
    status: str
    details: dict[str, Any] | None = None
    error_message: str | None = None


class JobRunner:
    """Execute a job with a consistent lifecycle and module_runs journaling."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
        lock_manager: JobLockManager | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()
        self._lock_manager = lock_manager or JobLockManager(
            session_factory=self._session_factory
        )
        self._logger = logging.getLogger(__name__)

    def run(self, context: RunContext, job: JobCallable) -> JobRunResult:
        """Run a job and persist lifecycle updates to module_runs."""
        lock_acquisition = self._lock_manager.acquire(context)
        if not lock_acquisition.acquired:
            return self._record_locked_run(
                context=context,
                lock_acquisition=lock_acquisition,
            )

        started_at = datetime.now(timezone.utc)
        run_record = ModuleRun(
            id=context.run_id,
            module_name=context.module_name,
            job_name=context.job_name,
            account_id=context.account_id,
            trigger_source=context.trigger_source,
            mode=context.mode,
            status="started",
            correlation_id=context.correlation_id,
            details_json=self._build_details(
                status="started",
                timestamp=started_at,
                message="Job run created.",
                lock_payload=self._build_lock_payload(
                    context=context,
                    acquisition=lock_acquisition,
                ),
            ),
            started_at=started_at,
        )

        with self._session_factory() as session:
            final_status = "error"
            try:
                session.add(run_record)
                session.commit()
                session.refresh(run_record)
                bind_run = getattr(self._lock_manager, "bind_run", None)
                lock_bound = True
                if callable(bind_run):
                    lock_bound = bind_run(
                        acquisition=lock_acquisition,
                        run_id=context.run_id,
                        account_id=context.account_id,
                    )
                if not lock_bound:
                    self._logger.warning(
                        "Job lock could not be linked to module_runs row",
                        extra=self._log_fields(context=context, status="lock_unbound"),
                    )

                self._logger.info(
                    "Job run started",
                    extra=self._log_fields(context=context, status="started"),
                )

                try:
                    payload = job(context) or {}
                except Exception as exc:
                    result = self._finish_with_error(
                        session=session,
                        run_record=run_record,
                        context=context,
                        error=exc,
                    )
                else:
                    result = self._finish_with_success(
                        session=session,
                        run_record=run_record,
                        context=context,
                        payload=payload,
                    )

                final_status = result.status
                return result
            finally:
                self._lock_manager.release(
                    acquisition=lock_acquisition,
                    final_status=final_status,
                )

    def _finish_with_success(
        self,
        *,
        session: Session,
        run_record: ModuleRun,
        context: RunContext,
        payload: dict[str, Any],
    ) -> JobRunResult:
        finished_at = datetime.now(timezone.utc)
        run_record.status = "success"
        run_record.finished_at = finished_at
        run_record.details_json = self._append_event(
            current_details=run_record.details_json,
            status="success",
            timestamp=finished_at,
            message="Job run finished successfully.",
            job_output=payload,
        )

        session.add(run_record)
        session.commit()
        session.refresh(run_record)

        self._logger.info(
            "Job run finished successfully",
            extra=self._log_fields(context=context, status="success"),
        )

        return self._build_result(context=context, run_record=run_record)

    def _finish_with_error(
        self,
        *,
        session: Session,
        run_record: ModuleRun,
        context: RunContext,
        error: Exception,
    ) -> JobRunResult:
        finished_at = datetime.now(timezone.utc)
        run_record.status = "error"
        run_record.finished_at = finished_at
        run_record.error_message = str(error)
        run_record.details_json = self._append_event(
            current_details=run_record.details_json,
            status="error",
            timestamp=finished_at,
            message="Job run finished with error.",
            error_payload={
                "exception_type": error.__class__.__name__,
                "message": str(error),
            },
        )

        session.add(run_record)
        session.commit()
        session.refresh(run_record)

        self._logger.exception(
            "Job run failed",
            extra=self._log_fields(context=context, status="error"),
        )

        return self._build_result(context=context, run_record=run_record)

    @staticmethod
    def _build_details(
        *,
        status: RunStatus,
        timestamp: datetime,
        message: str,
        lock_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        details = {
            "events": [
                {
                    "status": status,
                    "timestamp": timestamp.isoformat(),
                    "message": message,
                }
            ]
        }
        if lock_payload is not None:
            details["lock"] = lock_payload
        return details

    def _append_event(
        self,
        *,
        current_details: dict[str, Any] | None,
        status: RunStatus,
        timestamp: datetime,
        message: str,
        job_output: dict[str, Any] | None = None,
        error_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        details = {
            "events": list((current_details or {}).get("events", [])),
        }
        details["events"].append(
            {
                "status": status,
                "timestamp": timestamp.isoformat(),
                "message": message,
            }
        )

        if current_details and "lock" in current_details:
            details["lock"] = current_details["lock"]
        if current_details and "job_output" in current_details:
            details["job_output"] = current_details["job_output"]
        if current_details and "error" in current_details:
            details["error"] = current_details["error"]

        if job_output is not None:
            details["job_output"] = job_output
        if error_payload is not None:
            details["error"] = error_payload

        return details

    def _record_locked_run(
        self,
        *,
        context: RunContext,
        lock_acquisition: JobLockAcquisition,
    ) -> JobRunResult:
        timestamp = datetime.now(timezone.utc)
        message = "Job execution skipped because another run already holds the lock."
        run_record = ModuleRun(
            id=context.run_id,
            module_name=context.module_name,
            job_name=context.job_name,
            account_id=context.account_id,
            trigger_source=context.trigger_source,
            mode=context.mode,
            status="locked",
            correlation_id=context.correlation_id,
            details_json=self._build_details(
                status="locked",
                timestamp=timestamp,
                message=message,
                lock_payload=self._build_lock_payload(
                    context=context,
                    acquisition=lock_acquisition,
                ),
            ),
            error_message=message,
            started_at=timestamp,
            finished_at=timestamp,
        )

        with self._session_factory() as session:
            session.add(run_record)
            session.commit()
            session.refresh(run_record)

        self._logger.info(
            "Job run skipped because lock is already held",
            extra=self._log_fields(context=context, status="locked"),
        )
        return self._build_result(context=context, run_record=run_record)

    @staticmethod
    def _log_fields(*, context: RunContext, status: str) -> dict[str, Any]:
        return {
            "run_id": str(context.run_id),
            "correlation_id": context.correlation_id,
            "module_name": context.module_name,
            "job_name": context.job_name,
            "trigger_source": context.trigger_source,
            "mode": context.mode,
            "account_id": str(context.account_id) if context.account_id else None,
            "logical_scope": context.logical_scope,
            "status": status,
        }

    @staticmethod
    def _build_lock_payload(
        *,
        context: RunContext,
        acquisition: JobLockAcquisition,
    ) -> dict[str, Any]:
        return {
            "scope": acquisition.scope,
            "key": acquisition.key,
            "logical_scope": context.logical_scope,
            "acquired": acquisition.acquired,
            "holder_run_id": (
                str(acquisition.holder_run_id) if acquisition.holder_run_id else None
            ),
            "locked_until": (
                acquisition.locked_until.isoformat()
                if acquisition.locked_until
                else None
            ),
            "reason": acquisition.reason,
        }

    @staticmethod
    def _build_result(
        *,
        context: RunContext,
        run_record: ModuleRun,
    ) -> JobRunResult:
        return JobRunResult(
            run_id=str(run_record.id),
            correlation_id=context.correlation_id,
            module_name=context.module_name,
            job_name=context.job_name,
            trigger_source=context.trigger_source,
            mode=context.mode,
            account_id=str(context.account_id) if context.account_id else None,
            status=run_record.status,
            details=run_record.details_json,
            error_message=run_record.error_message,
        )
