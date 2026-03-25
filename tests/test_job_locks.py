from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import threading
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db import IdempotencyKey, ModuleRun, get_session_factory
from app.jobs import JobLockManager, JobRunner, RunContext


pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("require_postgresql"),
]


def _build_context(job_name: str) -> RunContext:
    return RunContext(
        module_name="module0",
        job_name=job_name,
        trigger_source="manual",
        mode="dry_run",
    )


def test_job_runner_blocks_parallel_duplicate_runs_across_trigger_sources() -> None:
    session_factory = get_session_factory()
    lock_manager = JobLockManager(session_factory=session_factory, lock_timeout_seconds=30)
    runner = JobRunner(session_factory=session_factory, lock_manager=lock_manager)
    job_name = f"lock-job-{uuid4().hex[:10]}"
    started = threading.Event()
    release = threading.Event()
    first_result: dict[str, object] = {}
    first_error: dict[str, BaseException] = {}

    first_context = RunContext(
        module_name="module0",
        job_name=job_name,
        trigger_source="manual",
        mode="dry_run",
    )
    second_context = RunContext(
        module_name="module0",
        job_name=job_name,
        trigger_source="scheduler",
        mode="dry_run",
    )

    def slow_job(_context: RunContext) -> dict[str, str]:
        started.set()
        if not release.wait(timeout=5):
            raise RuntimeError("Timed out while waiting to release test job lock.")
        return {"message": "slow-pong"}

    def run_first() -> None:
        try:
            first_result["result"] = runner.run(context=first_context, job=slow_job)
        except BaseException as exc:
            first_error["error"] = exc
        finally:
            release.set()

    worker = threading.Thread(target=run_first)
    worker.start()
    assert started.wait(timeout=5), "First job did not start in time."

    blocked_result = runner.run(
        context=second_context,
        job=lambda _context: {"message": "fast-pong"},
    )

    release.set()
    worker.join(timeout=5)
    assert worker.is_alive() is False, "First job thread did not finish in time."
    assert "error" not in first_error

    completed_result = first_result["result"]
    assert completed_result.status == "success"
    assert blocked_result.status == "locked"
    assert blocked_result.error_message == (
        "Job execution skipped because another run already holds the lock."
    )
    assert blocked_result.details["lock"]["reason"] == "already_running"
    assert blocked_result.details["lock"]["holder_run_id"] == completed_result.run_id

    with session_factory() as session:
        run_rows = session.execute(
            select(ModuleRun).where(
                ModuleRun.id.in_([UUID(completed_result.run_id), UUID(blocked_result.run_id)])
            )
        ).scalars().all()
        lock_row = session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == "job-lock",
                IdempotencyKey.key == lock_manager.build_lock_key(first_context),
            )
        ).scalar_one()

    run_statuses = {str(row.id): row.status for row in run_rows}
    assert run_statuses[completed_result.run_id] == "success"
    assert run_statuses[blocked_result.run_id] == "locked"
    assert lock_row.status == "released"


@pytest.mark.parametrize("final_status", ["success", "error"])
def test_released_job_lock_is_reacquired_normally(
    final_status: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.jobs.locks")
    session_factory = get_session_factory()
    lock_manager = JobLockManager(session_factory=session_factory, lock_timeout_seconds=30)
    job_name = f"released-lock-job-{uuid4().hex[:10]}"

    first_context = _build_context(job_name)
    second_context = _build_context(job_name)

    first_lock = lock_manager.acquire(first_context)
    assert first_lock.acquired is True
    assert first_lock.reason == "acquired"

    caplog.clear()
    released = lock_manager.release(
        acquisition=first_lock,
        final_status=final_status,
    )
    assert released is True
    assert any(record.getMessage() == "Job lock released" for record in caplog.records)

    caplog.clear()
    second_lock = lock_manager.acquire(second_context)

    assert second_lock.acquired is True
    assert second_lock.reason == "acquired"
    assert any(record.getMessage() == "Job lock acquired" for record in caplog.records)
    assert all(
        record.getMessage() != "Job lock acquired by reclaiming stale lock"
        for record in caplog.records
    )

    with session_factory() as session:
        lock_row = session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == "job-lock",
                IdempotencyKey.key == first_lock.key,
            )
        ).scalar_one()

    assert lock_row.status == "locked"
    assert lock_row.payload_hash == str(second_context.run_id)

    assert lock_manager.release(acquisition=second_lock, final_status="success") is True


def test_job_lock_can_be_reused_after_timeout_without_releasing_previous_owner(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.jobs.locks")
    session_factory = get_session_factory()
    lock_manager = JobLockManager(session_factory=session_factory, lock_timeout_seconds=30)
    job_name = f"stale-lock-job-{uuid4().hex[:10]}"

    first_context = _build_context(job_name)
    second_context = RunContext(
        module_name="module0",
        job_name=job_name,
        trigger_source="retry",
        mode="live",
    )

    first_lock = lock_manager.acquire(first_context)
    assert first_lock.acquired is True

    with session_factory() as session:
        lock_row = session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == "job-lock",
                IdempotencyKey.key == first_lock.key,
            )
        ).scalar_one()
        lock_row.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.add(lock_row)
        session.commit()

    caplog.clear()
    second_lock = lock_manager.acquire(second_context)

    assert second_lock.acquired is True
    assert second_lock.reason == "reclaimed"
    assert second_lock.run_id == second_context.run_id
    assert second_lock.run_id != first_lock.run_id
    assert any(
        record.getMessage() == "Job lock acquired by reclaiming stale lock"
        for record in caplog.records
    )

    stale_release = lock_manager.release(acquisition=first_lock, final_status="success")
    active_release = lock_manager.release(acquisition=second_lock, final_status="success")

    assert stale_release is False
    assert active_release is True

    with session_factory() as session:
        lock_row = session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == "job-lock",
                IdempotencyKey.key == first_lock.key,
            )
        ).scalar_one()

    assert lock_row.payload_hash == str(second_context.run_id)
    assert lock_row.status == "released"
