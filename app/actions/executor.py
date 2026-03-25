"""Shared executor for Action layer calls with audit and idempotency."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.actions.base import ActionResult, BaseAction
from app.db.models import ActionLog, IdempotencyKey
from app.db.session import get_session_factory
from app.jobs.context import RunMode

DEDUPLICATED_FINAL_STATUSES = frozenset({"completed", "dry_run"})
LOCKED_STATUSES = frozenset({"reserved"})
RETRYABLE_STATUSES = frozenset({"error"})


class ActionExecutor:
    """Execute actions through one audited, idempotent pathway.

    Semantic split:
    - logical action: unique row in idempotency_keys for scope+key
    - execution attempt: one row in action_logs per actual try
    - latest known final state: idempotency_keys.status
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Any | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()
        self._logger = logging.getLogger(__name__)

    def execute(
        self,
        *,
        action: BaseAction,
        mode: RunMode,
        run_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> ActionResult:
        """Run a single action with dry-run/live branching and audit logging."""
        correlation_value = correlation_id or uuid4().hex
        request_payload = action.build_request_payload()
        payload_hash = self._hash_payload(request_payload)
        idempotency_key = action.build_idempotency_key()
        scope = self._build_scope(action=action, mode=mode)

        self._logger.info(
            "Action execution requested",
            extra=self._log_fields(
                action=action,
                mode=mode,
                run_id=run_id,
                correlation_id=correlation_value,
                status="requested",
                idempotency_key=idempotency_key,
            ),
        )

        with self._session_factory() as session:
            existing_key = self._load_idempotency_key(
                session=session,
                scope=scope,
                key=idempotency_key,
            )
            if existing_key is not None:
                existing_resolution = self._handle_existing_key(
                    session=session,
                    action=action,
                    existing_key=existing_key,
                    payload_hash=payload_hash,
                    request_payload=request_payload,
                    mode=mode,
                    run_id=run_id,
                    correlation_id=correlation_value,
                )
                if isinstance(existing_resolution, ActionResult):
                    return existing_resolution
                reservation = existing_resolution
            else:
                reservation = IdempotencyKey(
                    scope=scope,
                    key=idempotency_key,
                    account_id=action.account_id,
                    run_id=run_id,
                    status="reserved",
                    payload_hash=payload_hash,
                    locked_until=None,
                    last_seen_at=self._utcnow(),
                )
                session.add(reservation)

                try:
                    session.flush()
                except IntegrityError:
                    session.rollback()
                    existing_key = self._load_idempotency_key(
                        session=session,
                        scope=scope,
                        key=idempotency_key,
                    )
                    if existing_key is not None:
                        existing_resolution = self._handle_existing_key(
                            session=session,
                            action=action,
                            existing_key=existing_key,
                            payload_hash=payload_hash,
                            request_payload=request_payload,
                            mode=mode,
                            run_id=run_id,
                            correlation_id=correlation_value,
                        )
                        if isinstance(existing_resolution, ActionResult):
                            return existing_resolution
                        reservation = existing_resolution
                    else:
                        raise

            try:
                result_payload = (
                    action.run_dry() if mode == "dry_run" else action.run_live()
                )
            except Exception as exc:
                return self._finish_error(
                    session=session,
                    action=action,
                    reservation=reservation,
                    request_payload=request_payload,
                    mode=mode,
                    run_id=run_id,
                    correlation_id=correlation_value,
                    idempotency_key=idempotency_key,
                    error=exc,
                )

            return self._finish_success(
                session=session,
                action=action,
                reservation=reservation,
                request_payload=request_payload,
                result_payload=result_payload,
                mode=mode,
                run_id=run_id,
                correlation_id=correlation_value,
                idempotency_key=idempotency_key,
            )

    def _handle_existing_key(
        self,
        *,
        session: Session,
        action: BaseAction,
        existing_key: IdempotencyKey,
        payload_hash: str,
        request_payload: dict[str, Any],
        mode: RunMode,
        run_id: UUID | None,
        correlation_id: str,
    ) -> ActionResult | IdempotencyKey:
        if existing_key.payload_hash and existing_key.payload_hash != payload_hash:
            return self._finish_collision_error(
                session=session,
                action=action,
                existing_key=existing_key,
                request_payload=request_payload,
                mode=mode,
                run_id=run_id,
                correlation_id=correlation_id,
            )

        existing_key.last_seen_at = self._utcnow()

        if existing_key.status in RETRYABLE_STATUSES:
            existing_key.status = "reserved"
            existing_key.run_id = run_id
            existing_key.account_id = action.account_id
            session.add(existing_key)
            session.flush()

            self._logger.info(
                "Retrying logical action after previous error",
                extra=self._log_fields(
                    action=action,
                    mode=mode,
                    run_id=run_id,
                    correlation_id=correlation_id,
                    status="retrying",
                    idempotency_key=existing_key.key,
                ),
            )
            return existing_key

        duplicate_reason = "completed"
        if existing_key.status in LOCKED_STATUSES:
            duplicate_reason = "locked"
        elif existing_key.status in DEDUPLICATED_FINAL_STATUSES:
            duplicate_reason = "final_result"

        result_payload = {
            "duplicate": True,
            "duplicate_of_scope": existing_key.scope,
            "existing_status": existing_key.status,
            "duplicate_reason": duplicate_reason,
            "external_effect_applied": False,
        }
        action_log = ActionLog(
            module_name=action.module_name,
            action_name=action.action_name,
            account_id=action.account_id,
            run_id=run_id,
            mode=mode,
            status="duplicate",
            idempotency_key=existing_key.key,
            request_payload=request_payload,
            result_payload=result_payload,
            error_message=None,
        )
        session.add(existing_key)
        session.add(action_log)
        session.commit()
        session.refresh(action_log)

        self._logger.info(
            "Action execution deduplicated",
            extra=self._log_fields(
                action=action,
                mode=mode,
                run_id=run_id,
                correlation_id=correlation_id,
                status="duplicate",
                idempotency_key=existing_key.key,
            ),
        )

        return self._build_result(
            action_log=action_log,
            action=action,
            run_id=run_id,
            correlation_id=correlation_id,
            duplicate=True,
        )

    def _finish_success(
        self,
        *,
        session: Session,
        action: BaseAction,
        reservation: IdempotencyKey,
        request_payload: dict[str, Any],
        result_payload: dict[str, Any],
        mode: RunMode,
        run_id: UUID | None,
        correlation_id: str,
        idempotency_key: str,
    ) -> ActionResult:
        reservation.status = "dry_run" if mode == "dry_run" else "completed"
        reservation.run_id = run_id
        reservation.account_id = action.account_id
        reservation.last_seen_at = self._utcnow()
        action_log = ActionLog(
            module_name=action.module_name,
            action_name=action.action_name,
            account_id=action.account_id,
            run_id=run_id,
            mode=mode,
            status="dry_run" if mode == "dry_run" else "success",
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            result_payload=result_payload,
            error_message=None,
        )
        session.add(reservation)
        session.add(action_log)
        session.commit()
        session.refresh(action_log)

        self._logger.info(
            "Action execution finished",
            extra=self._log_fields(
                action=action,
                mode=mode,
                run_id=run_id,
                correlation_id=correlation_id,
                status=action_log.status,
                idempotency_key=idempotency_key,
            ),
        )

        return self._build_result(
            action_log=action_log,
            action=action,
            run_id=run_id,
            correlation_id=correlation_id,
            duplicate=False,
        )

    def _finish_error(
        self,
        *,
        session: Session,
        action: BaseAction,
        reservation: IdempotencyKey,
        request_payload: dict[str, Any],
        mode: RunMode,
        run_id: UUID | None,
        correlation_id: str,
        idempotency_key: str,
        error: Exception,
    ) -> ActionResult:
        reservation.status = "error"
        reservation.run_id = run_id
        reservation.account_id = action.account_id
        reservation.last_seen_at = self._utcnow()
        action_log = ActionLog(
            module_name=action.module_name,
            action_name=action.action_name,
            account_id=action.account_id,
            run_id=run_id,
            mode=mode,
            status="error",
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            result_payload=None,
            error_message=str(error),
        )
        session.add(reservation)
        session.add(action_log)
        session.commit()
        session.refresh(action_log)

        self._logger.exception(
            "Action execution failed",
            extra=self._log_fields(
                action=action,
                mode=mode,
                run_id=run_id,
                correlation_id=correlation_id,
                status="error",
                idempotency_key=idempotency_key,
            ),
        )

        return self._build_result(
            action_log=action_log,
            action=action,
            run_id=run_id,
            correlation_id=correlation_id,
            duplicate=False,
        )

    def _finish_collision_error(
        self,
        *,
        session: Session,
        action: BaseAction,
        existing_key: IdempotencyKey,
        request_payload: dict[str, Any],
        mode: RunMode,
        run_id: UUID | None,
        correlation_id: str,
    ) -> ActionResult:
        existing_key.last_seen_at = self._utcnow()
        error_message = (
            "Idempotency key collision detected for different request payloads."
        )
        action_log = ActionLog(
            module_name=action.module_name,
            action_name=action.action_name,
            account_id=action.account_id,
            run_id=run_id,
            mode=mode,
            status="error",
            idempotency_key=existing_key.key,
            request_payload=request_payload,
            result_payload=None,
            error_message=error_message,
        )
        session.add(existing_key)
        session.add(action_log)
        session.commit()
        session.refresh(action_log)

        self._logger.error(
            "Action idempotency collision detected",
            extra=self._log_fields(
                action=action,
                mode=mode,
                run_id=run_id,
                correlation_id=correlation_id,
                status="error",
                idempotency_key=existing_key.key,
            ),
        )

        return self._build_result(
            action_log=action_log,
            action=action,
            run_id=run_id,
            correlation_id=correlation_id,
            duplicate=False,
        )

    @staticmethod
    def _load_idempotency_key(
        *,
        session: Session,
        scope: str,
        key: str,
    ) -> IdempotencyKey | None:
        return session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == scope,
                IdempotencyKey.key == key,
            )
        ).scalar_one_or_none()

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _log_fields(
        *,
        action: BaseAction,
        mode: RunMode,
        run_id: UUID | None,
        correlation_id: str,
        status: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return {
            "module_name": action.module_name,
            "action_name": action.action_name,
            "account_id": str(action.account_id) if action.account_id else None,
            "run_id": str(run_id) if run_id else None,
            "correlation_id": correlation_id,
            "mode": mode,
            "status": status,
            "idempotency_key": idempotency_key,
        }

    @staticmethod
    def _build_result(
        *,
        action_log: ActionLog,
        action: BaseAction,
        run_id: UUID | None,
        correlation_id: str,
        duplicate: bool,
    ) -> ActionResult:
        return ActionResult(
            action_log_id=str(action_log.id),
            module_name=action.module_name,
            action_name=action.action_name,
            account_id=str(action.account_id) if action.account_id else None,
            run_id=str(run_id) if run_id else None,
            correlation_id=correlation_id,
            mode=action_log.mode,
            status=action_log.status,
            idempotency_key=action_log.idempotency_key or "",
            duplicate=duplicate,
            request_payload=action_log.request_payload,
            result_payload=action_log.result_payload,
            error_message=action_log.error_message,
        )

    @staticmethod
    def _build_scope(*, action: BaseAction, mode: RunMode) -> str:
        """Separate dry-run and live idempotency domains."""
        return f"{action.idempotency_scope}:{mode}"
