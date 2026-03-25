from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.actions import ActionExecutor, execute_demo_action
from app.db import ActionLog, IdempotencyKey, get_session_factory


pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("require_postgresql"),
]


def test_demo_action_dry_run_logs_action_and_idempotency() -> None:
    message = f"test-action:{uuid4().hex}"
    result = execute_demo_action(
        target="test-target",
        message=message,
        mode="dry_run",
    )

    assert result.status == "dry_run"
    assert result.duplicate is False

    session_factory = get_session_factory()
    with session_factory() as session:
        action_log = session.get(ActionLog, UUID(result.action_log_id))
        idempotency_row = session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == "module0:demo_dispatch:dry_run",
                IdempotencyKey.key == result.idempotency_key,
            )
        ).scalar_one()

    assert action_log is not None
    assert action_log.status == "dry_run"
    assert action_log.request_payload["message"] == message
    assert action_log.result_payload["mock_effect_applied"] is False
    assert idempotency_row.status == "dry_run"


def test_demo_action_dry_run_duplicate_is_deduplicated() -> None:
    executor = ActionExecutor()
    message = f"test-duplicate:{uuid4().hex}"

    first = execute_demo_action(
        target="test-target",
        message=message,
        mode="dry_run",
        executor=executor,
    )
    second = execute_demo_action(
        target="test-target",
        message=message,
        mode="dry_run",
        executor=executor,
    )

    assert first.status == "dry_run"
    assert second.status == "duplicate"
    assert second.duplicate is True
    assert second.idempotency_key == first.idempotency_key

    session_factory = get_session_factory()
    with session_factory() as session:
        action_log_count = session.scalar(
            select(func.count())
            .select_from(ActionLog)
            .where(ActionLog.idempotency_key == first.idempotency_key)
        )
        idempotency_key_count = session.scalar(
            select(func.count())
            .select_from(IdempotencyKey)
            .where(
                IdempotencyKey.scope == "module0:demo_dispatch:dry_run",
                IdempotencyKey.key == first.idempotency_key,
            )
        )

    assert action_log_count == 2
    assert idempotency_key_count == 1


def test_demo_action_success_duplicate_is_deduplicated() -> None:
    executor = ActionExecutor()
    message = f"test-success-duplicate:{uuid4().hex}"

    first = execute_demo_action(
        target="test-target",
        message=message,
        mode="live",
        executor=executor,
    )
    second = execute_demo_action(
        target="test-target",
        message=message,
        mode="live",
        executor=executor,
    )

    assert first.status == "success"
    assert second.status == "duplicate"
    assert second.duplicate is True
    assert second.result_payload["existing_status"] == "completed"

    session_factory = get_session_factory()
    with session_factory() as session:
        action_log_statuses = list(
            session.execute(
                select(ActionLog.status)
                .where(ActionLog.idempotency_key == first.idempotency_key)
                .order_by(ActionLog.created_at)
            ).scalars()
        )

    assert action_log_statuses[-2:] == ["success", "duplicate"]


def test_demo_action_live_is_not_blocked_by_previous_dry_run() -> None:
    message = f"test-dry-then-live:{uuid4().hex}"

    dry_result = execute_demo_action(
        target="test-target",
        message=message,
        mode="dry_run",
    )
    live_result = execute_demo_action(
        target="test-target",
        message=message,
        mode="live",
    )

    assert dry_result.status == "dry_run"
    assert live_result.status == "success"
    assert live_result.duplicate is False
    assert live_result.result_payload["mock_effect_applied"] is True

    session_factory = get_session_factory()
    with session_factory() as session:
        dry_key_count = session.scalar(
            select(func.count())
            .select_from(IdempotencyKey)
            .where(
                IdempotencyKey.scope == "module0:demo_dispatch:dry_run",
                IdempotencyKey.key == dry_result.idempotency_key,
            )
        )
        live_key_count = session.scalar(
            select(func.count())
            .select_from(IdempotencyKey)
            .where(
                IdempotencyKey.scope == "module0:demo_dispatch:live",
                IdempotencyKey.key == live_result.idempotency_key,
            )
        )

    assert dry_key_count == 1
    assert live_key_count == 1


def test_demo_action_error_then_retry_success_creates_second_attempt() -> None:
    executor = ActionExecutor()
    message = f"test-retry-success:{uuid4().hex}"

    first = execute_demo_action(
        target="test-target",
        message=message,
        mode="live",
        should_fail=True,
        executor=executor,
    )
    second = execute_demo_action(
        target="test-target",
        message=message,
        mode="live",
        should_fail=False,
        executor=executor,
    )

    assert first.status == "error"
    assert second.status == "success"
    assert second.duplicate is False

    session_factory = get_session_factory()
    with session_factory() as session:
        action_logs = session.execute(
            select(ActionLog)
            .where(ActionLog.idempotency_key == first.idempotency_key)
            .order_by(ActionLog.created_at)
        ).scalars().all()
        idempotency_row = session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == "module0:demo_dispatch:live",
                IdempotencyKey.key == first.idempotency_key,
            )
        ).scalar_one()

    assert [log.status for log in action_logs[-2:]] == ["error", "success"]
    assert action_logs[-2].error_message == "Demo action failed on purpose."
    assert action_logs[-1].result_payload["mock_effect_applied"] is True
    assert idempotency_row.status == "completed"


def test_demo_action_error_then_retry_error_creates_new_attempt() -> None:
    executor = ActionExecutor()
    message = f"test-retry-error:{uuid4().hex}"

    first = execute_demo_action(
        target="test-target",
        message=message,
        mode="live",
        should_fail=True,
        executor=executor,
    )
    second = execute_demo_action(
        target="test-target",
        message=message,
        mode="live",
        should_fail=True,
        executor=executor,
    )

    assert first.status == "error"
    assert second.status == "error"
    assert second.duplicate is False

    session_factory = get_session_factory()
    with session_factory() as session:
        action_log_statuses = list(
            session.execute(
                select(ActionLog.status)
                .where(ActionLog.idempotency_key == first.idempotency_key)
                .order_by(ActionLog.created_at)
            ).scalars()
        )
        idempotency_row = session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == "module0:demo_dispatch:live",
                IdempotencyKey.key == first.idempotency_key,
            )
        ).scalar_one()

    assert action_log_statuses[-2:] == ["error", "error"]
    assert idempotency_row.status == "error"
