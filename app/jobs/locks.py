"""Cross-process lock manager for jobs backed by idempotency_keys."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings
from app.db.models import IdempotencyKey
from app.db.session import get_session_factory
from app.jobs.context import RunContext

JOB_LOCK_SCOPE = "job-lock"
JOB_LOCKED_STATUS = "locked"
JOB_RELEASED_STATUS = "released"


@dataclass(frozen=True)
class JobLockAcquisition:
    """Outcome of a single job-lock acquisition attempt."""

    acquired: bool
    scope: str
    key: str
    logical_scope: str
    run_id: UUID
    module_name: str
    job_name: str
    account_id: UUID | None
    correlation_id: str
    trigger_source: str
    mode: str
    holder_run_id: UUID | None
    locked_until: datetime | None
    row_id: UUID | None = None
    reason: str | None = None


class JobLockManager:
    """Prevent duplicate job execution across processes and containers."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
        lock_timeout_seconds: int | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()
        self._lock_timeout_seconds = (
            lock_timeout_seconds
            if lock_timeout_seconds is not None
            else get_settings().job_lock_timeout_seconds
        )
        self._logger = logging.getLogger(__name__)

    def acquire(self, context: RunContext) -> JobLockAcquisition:
        """Reserve a job lock or return the active conflicting lock."""
        scope = JOB_LOCK_SCOPE
        key = self.build_lock_key(context)

        while True:
            now = self._utcnow()
            locked_until = now + timedelta(seconds=self._lock_timeout_seconds)

            with self._session_factory() as session:
                lock_row = session.execute(
                    select(IdempotencyKey)
                    .where(
                        IdempotencyKey.scope == scope,
                        IdempotencyKey.key == key,
                    )
                    .with_for_update()
                ).scalar_one_or_none()

                if lock_row is None:
                    lock_row = IdempotencyKey(
                        scope=scope,
                        key=key,
                        account_id=context.account_id,
                        run_id=None,
                        status=JOB_LOCKED_STATUS,
                        payload_hash=str(context.run_id),
                        locked_until=locked_until,
                        last_seen_at=now,
                    )
                    session.add(lock_row)

                    try:
                        session.commit()
                    except IntegrityError:
                        session.rollback()
                        continue

                    session.refresh(lock_row)
                    self._logger.info(
                        "Job lock acquired",
                        extra=self._log_fields(
                            context=context,
                            status="acquired",
                            key=key,
                            locked_until=lock_row.locked_until,
                            holder_run_id=self._extract_holder_run_id(lock_row),
                        ),
                    )
                    return self._build_acquisition(
                        context=context,
                        key=key,
                        row=lock_row,
                        acquired=True,
                        reason="acquired",
                    )

                active_conflict = (
                    lock_row.status == JOB_LOCKED_STATUS
                    and lock_row.locked_until is not None
                    and lock_row.locked_until > now
                )
                if active_conflict:
                    holder_run_id = self._extract_holder_run_id(lock_row)
                    row_id = lock_row.id
                    current_locked_until = lock_row.locked_until
                    session.rollback()
                    self._logger.info(
                        "Job lock already held by another run",
                        extra=self._log_fields(
                            context=context,
                            status="already_running",
                            key=key,
                            locked_until=current_locked_until,
                            holder_run_id=holder_run_id,
                        ),
                    )
                    return JobLockAcquisition(
                        acquired=False,
                        scope=scope,
                        key=key,
                        logical_scope=context.logical_scope,
                        run_id=context.run_id,
                        module_name=context.module_name,
                        job_name=context.job_name,
                        account_id=context.account_id,
                        correlation_id=context.correlation_id,
                        trigger_source=context.trigger_source,
                        mode=context.mode,
                        holder_run_id=holder_run_id,
                        locked_until=current_locked_until,
                        row_id=row_id,
                        reason="already_running",
                    )

                reclaiming_stale_lock = lock_row.status == JOB_LOCKED_STATUS
                lock_row.last_seen_at = now
                lock_row.status = JOB_LOCKED_STATUS
                lock_row.account_id = context.account_id
                lock_row.run_id = None
                lock_row.payload_hash = str(context.run_id)
                lock_row.locked_until = locked_until
                lock_row.last_seen_at = now
                session.add(lock_row)
                session.commit()
                session.refresh(lock_row)

                if reclaiming_stale_lock:
                    self._logger.info(
                        "Job lock acquired by reclaiming stale lock",
                        extra=self._log_fields(
                            context=context,
                            status="reclaimed",
                            key=key,
                            locked_until=lock_row.locked_until,
                            holder_run_id=self._extract_holder_run_id(lock_row),
                        ),
                    )
                else:
                    self._logger.info(
                        "Job lock acquired",
                        extra=self._log_fields(
                            context=context,
                            status="acquired",
                            key=key,
                            locked_until=lock_row.locked_until,
                            holder_run_id=self._extract_holder_run_id(lock_row),
                        ),
                    )
                return self._build_acquisition(
                    context=context,
                    key=key,
                    row=lock_row,
                    acquired=True,
                    reason="reclaimed" if reclaiming_stale_lock else "acquired",
                )

    def bind_run(
        self,
        *,
        acquisition: JobLockAcquisition,
        run_id: UUID,
        account_id: UUID | None,
    ) -> bool:
        """Attach an existing module_runs row to an already acquired lock."""
        if not acquisition.acquired:
            return False

        with self._session_factory() as session:
            lock_row = session.execute(
                select(IdempotencyKey)
                .where(
                    IdempotencyKey.scope == acquisition.scope,
                    IdempotencyKey.key == acquisition.key,
                )
                .with_for_update()
            ).scalar_one_or_none()

            if lock_row is None:
                session.rollback()
                return False

            if (
                lock_row.status != JOB_LOCKED_STATUS
                or lock_row.payload_hash != str(acquisition.run_id)
            ):
                session.rollback()
                return False

            lock_row.run_id = run_id
            lock_row.account_id = account_id
            lock_row.last_seen_at = self._utcnow()
            session.add(lock_row)
            session.commit()
            return True

    def release(
        self,
        *,
        acquisition: JobLockAcquisition,
        final_status: str,
    ) -> bool:
        """Release a previously acquired job lock if this run still owns it."""
        if not acquisition.acquired:
            return False

        with self._session_factory() as session:
            lock_row = session.execute(
                select(IdempotencyKey)
                .where(
                    IdempotencyKey.scope == acquisition.scope,
                    IdempotencyKey.key == acquisition.key,
                )
                .with_for_update()
            ).scalar_one_or_none()

            if lock_row is None:
                session.rollback()
                self._logger.warning(
                    "Job lock row disappeared before release",
                    extra=self._release_log_fields(acquisition=acquisition, final_status=final_status),
                )
                return False

            if (
                lock_row.status != JOB_LOCKED_STATUS
                or lock_row.payload_hash != str(acquisition.run_id)
            ):
                session.rollback()
                self._logger.info(
                    "Skipping job lock release because ownership changed",
                    extra=self._release_log_fields(
                        acquisition=acquisition,
                        final_status=final_status,
                    ),
                )
                return False

            now = self._utcnow()
            lock_row.status = JOB_RELEASED_STATUS
            lock_row.locked_until = now
            lock_row.last_seen_at = now
            session.add(lock_row)
            session.commit()

            self._logger.info(
                "Job lock released",
                extra=self._release_log_fields(
                    acquisition=acquisition,
                    final_status=final_status,
                ),
            )
            return True

    @staticmethod
    def build_lock_identity(context: RunContext) -> str:
        """Return the stable logical identity for a job lock."""
        account_part = str(context.account_id) if context.account_id else "global"
        return (
            f"{context.module_name}|{context.job_name}|"
            f"{account_part}|{context.logical_scope}"
        )

    def build_lock_key(self, context: RunContext) -> str:
        """Return a compact key suitable for the idempotency_keys table."""
        identity = self.build_lock_identity(context)
        return sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _build_acquisition(
        *,
        context: RunContext,
        key: str,
        row: IdempotencyKey,
        acquired: bool,
        reason: str,
    ) -> JobLockAcquisition:
        return JobLockAcquisition(
            acquired=acquired,
            scope=row.scope,
            key=key,
            logical_scope=context.logical_scope,
            run_id=context.run_id,
            module_name=context.module_name,
            job_name=context.job_name,
            account_id=context.account_id,
            correlation_id=context.correlation_id,
            trigger_source=context.trigger_source,
            mode=context.mode,
            holder_run_id=context.run_id if acquired else row.run_id,
            locked_until=row.locked_until,
            row_id=row.id,
            reason=reason,
        )

    @staticmethod
    def _extract_holder_run_id(row: IdempotencyKey) -> UUID | None:
        if row.run_id is not None:
            return row.run_id
        if row.payload_hash:
            try:
                return UUID(row.payload_hash)
            except ValueError:
                return None
        return None

    @staticmethod
    def _log_fields(
        *,
        context: RunContext,
        status: str,
        key: str,
        locked_until: datetime | None,
        holder_run_id: UUID | None,
    ) -> dict[str, str | None]:
        return {
            "module_name": context.module_name,
            "job_name": context.job_name,
            "account_id": str(context.account_id) if context.account_id else None,
            "logical_scope": context.logical_scope,
            "run_id": str(context.run_id),
            "correlation_id": context.correlation_id,
            "trigger_source": context.trigger_source,
            "status": status,
            "job_lock_key": key,
            "holder_run_id": str(holder_run_id) if holder_run_id else None,
            "locked_until": locked_until.isoformat() if locked_until else None,
        }

    @staticmethod
    def _release_log_fields(
        *,
        acquisition: JobLockAcquisition,
        final_status: str,
    ) -> dict[str, str | None]:
        return {
            "module_name": acquisition.module_name,
            "job_name": acquisition.job_name,
            "run_id": str(acquisition.run_id),
            "correlation_id": acquisition.correlation_id,
            "account_id": str(acquisition.account_id) if acquisition.account_id else None,
            "logical_scope": acquisition.logical_scope,
            "trigger_source": acquisition.trigger_source,
            "mode": acquisition.mode,
            "status": final_status,
            "job_lock_key": acquisition.key,
            "holder_run_id": (
                str(acquisition.holder_run_id) if acquisition.holder_run_id else None
            ),
            "locked_until": (
                acquisition.locked_until.isoformat() if acquisition.locked_until else None
            ),
        }
