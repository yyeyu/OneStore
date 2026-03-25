from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import app.cli.app as cli_app_module

from typer.testing import CliRunner

from app.jobs import JobLockAcquisition, JobRunner, PingJob, RunContext
from app.jobs.runner import JobRunResult
from app.main import cli


runner = CliRunner()


class FakeSession:
    def __init__(self):
        self.added: list[Any] = []
        self.commits = 0
        self.refreshed: list[Any] = []
        self.closed = False

    def add(self, obj: Any) -> None:
        if obj not in self.added:
            self.added.append(obj)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, obj: Any) -> None:
        self.refreshed.append(obj)

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class StubLockManager:
    def __init__(self, *, acquired: bool = True, reason: str = "acquired"):
        self.acquired = acquired
        self.reason = reason
        self.acquire_calls: list[RunContext] = []
        self.release_calls: list[tuple[JobLockAcquisition, str]] = []
        self.holder_run_id = uuid4()

    def acquire(self, context: RunContext) -> JobLockAcquisition:
        self.acquire_calls.append(context)
        return JobLockAcquisition(
            acquired=self.acquired,
            scope="job-lock",
            key="job-lock-key",
            logical_scope=context.logical_scope,
            run_id=context.run_id,
            module_name=context.module_name,
            job_name=context.job_name,
            account_id=context.account_id,
            correlation_id=context.correlation_id,
            trigger_source=context.trigger_source,
            mode=context.mode,
            holder_run_id=context.run_id if self.acquired else self.holder_run_id,
            locked_until=datetime.now(timezone.utc),
            row_id=None,
            reason=self.reason,
        )

    def release(self, *, acquisition: JobLockAcquisition, final_status: str) -> bool:
        self.release_calls.append((acquisition, final_status))
        return acquisition.acquired


def test_run_context_generates_ids_and_defaults() -> None:
    context = RunContext(
        module_name="module0",
        job_name="ping",
        trigger_source="manual",
        mode="dry_run",
    )

    assert context.module_name == "module0"
    assert context.job_name == "ping"
    assert context.trigger_source == "manual"
    assert context.mode == "dry_run"
    assert context.run_id is not None
    assert context.correlation_id


def test_job_runner_records_success_lifecycle() -> None:
    fake_session = FakeSession()
    lock_manager = StubLockManager()
    runner_instance = JobRunner(
        session_factory=lambda: fake_session,
        lock_manager=lock_manager,
    )
    context = RunContext(
        module_name="module0",
        job_name="ping",
        trigger_source="manual",
        mode="dry_run",
    )

    result = runner_instance.run(context=context, job=PingJob())
    run_record = fake_session.added[0]

    assert result.status == "success"
    assert run_record.status == "success"
    assert run_record.id == context.run_id
    assert fake_session.commits == 2
    assert run_record.details_json["events"][0]["status"] == "started"
    assert run_record.details_json["events"][-1]["status"] == "success"
    assert run_record.details_json["job_output"]["message"] == "pong"
    assert run_record.details_json["lock"]["acquired"] is True
    assert lock_manager.release_calls[-1][1] == "success"


def test_job_runner_records_error_lifecycle() -> None:
    fake_session = FakeSession()
    lock_manager = StubLockManager()
    runner_instance = JobRunner(
        session_factory=lambda: fake_session,
        lock_manager=lock_manager,
    )
    context = RunContext(
        module_name="module0",
        job_name="ping",
        trigger_source="manual",
        mode="live",
    )

    result = runner_instance.run(context=context, job=PingJob(should_fail=True))
    run_record = fake_session.added[0]

    assert result.status == "error"
    assert result.error_message == "Demo ping job failed on purpose."
    assert run_record.status == "error"
    assert run_record.details_json["events"][0]["status"] == "started"
    assert run_record.details_json["events"][-1]["status"] == "error"
    assert run_record.details_json["error"]["exception_type"] == "RuntimeError"
    assert lock_manager.release_calls[-1][1] == "error"


def test_job_runner_records_locked_lifecycle_without_running_job() -> None:
    fake_session = FakeSession()
    lock_manager = StubLockManager(acquired=False, reason="already_running")
    runner_instance = JobRunner(
        session_factory=lambda: fake_session,
        lock_manager=lock_manager,
    )
    context = RunContext(
        module_name="module0",
        job_name="ping",
        trigger_source="scheduler",
        mode="dry_run",
    )
    executed = False

    def job(_context: RunContext) -> dict[str, Any]:
        nonlocal executed
        executed = True
        return {"message": "should not run"}

    result = runner_instance.run(context=context, job=job)
    run_record = fake_session.added[0]

    assert result.status == "locked"
    assert result.error_message == (
        "Job execution skipped because another run already holds the lock."
    )
    assert executed is False
    assert run_record.status == "locked"
    assert run_record.details_json["events"][0]["status"] == "locked"
    assert run_record.details_json["lock"]["reason"] == "already_running"
    assert run_record.details_json["lock"]["holder_run_id"] == str(
        lock_manager.holder_run_id
    )
    assert fake_session.commits == 1
    assert lock_manager.release_calls == []


def test_run_test_job_command(monkeypatch) -> None:
    def fake_run_registered_job(**kwargs):
        return JobRunResult(
            run_id="run-1",
            correlation_id="corr-1",
            module_name="module0",
            job_name=kwargs["job_name"],
            trigger_source=kwargs["trigger_source"],
            mode=kwargs["mode"],
            account_id=None,
            status="success",
            details={"events": []},
            error_message=None,
        )

    monkeypatch.setattr(
        cli_app_module,
        "run_registered_job",
        fake_run_registered_job,
    )

    result = runner.invoke(cli, ["run-test-job"])

    assert result.exit_code == 0
    assert '"status": "success"' in result.stdout


def test_run_test_job_command_returns_error_exit_code(monkeypatch) -> None:
    def fake_run_registered_job(**kwargs):
        return JobRunResult(
            run_id="run-2",
            correlation_id="corr-2",
            module_name="module0",
            job_name=kwargs["job_name"],
            trigger_source=kwargs["trigger_source"],
            mode=kwargs["mode"],
            account_id=None,
            status="error",
            details={"events": []},
            error_message="boom",
        )

    monkeypatch.setattr(
        cli_app_module,
        "run_registered_job",
        fake_run_registered_job,
    )

    result = runner.invoke(cli, ["run-test-job", "--fail"])

    assert result.exit_code == 1
    assert '"status": "error"' in result.stdout
