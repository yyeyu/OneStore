from __future__ import annotations

from typing import Any

import app.cli.app as cli_app_module
from typer.testing import CliRunner

from app.jobs import JobRunner, RunContext, SystemProbeJob
from app.jobs.runner import JobRunResult
from app.main import cli


runner = CliRunner()


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits = 0
        self.refreshed: list[Any] = []
        self.closed = False
        self._next_id = 1

    def add(self, obj: Any) -> None:
        if hasattr(obj, "id") and getattr(obj, "id") is None:
            setattr(obj, "id", self._next_id)
            self._next_id += 1
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


def test_run_context_has_minimal_fields() -> None:
    context = RunContext(
        module_name="system_core",
        job_name="system-probe",
        trigger_source="manual",
    )

    assert context.module_name == "system_core"
    assert context.job_name == "system-probe"
    assert context.trigger_source == "manual"
    assert context.account_id is None


def test_job_runner_records_success_lifecycle() -> None:
    fake_session = FakeSession()
    runner_instance = JobRunner(session_factory=lambda: fake_session)
    context = RunContext(
        module_name="system_core",
        job_name="system-probe",
        trigger_source="manual",
    )

    result = runner_instance.run(context=context, module_id=1, job=SystemProbeJob())
    run_record = fake_session.added[0]

    assert result.status == "success"
    assert run_record.status == "success"
    assert result.run_id == run_record.id
    assert result.module_id == 1
    assert fake_session.commits == 2


def test_job_runner_records_error_lifecycle() -> None:
    fake_session = FakeSession()
    runner_instance = JobRunner(session_factory=lambda: fake_session)
    context = RunContext(
        module_name="system_core",
        job_name="system-probe",
        trigger_source="manual",
    )

    result = runner_instance.run(
        context=context,
        module_id=1,
        job=SystemProbeJob(should_fail=True),
    )
    run_record = fake_session.added[0]

    assert result.status == "error"
    assert result.error_message == "System probe job failed on purpose."
    assert run_record.status == "error"
    assert fake_session.commits == 2


def test_run_system_probe_command(monkeypatch) -> None:
    def fake_run_registered_job(**kwargs):
        return JobRunResult(
            run_id=1,
            module_id=1,
            module_name="system_core",
            job_name=kwargs["job_name"],
            trigger_source=kwargs["trigger_source"],
            account_id=kwargs.get("account_id"),
            status="success",
            error_message=None,
            payload={"message": "system_probe_ok"},
        )

    monkeypatch.setattr(cli_app_module, "run_registered_job", fake_run_registered_job)

    result = runner.invoke(cli, ["run-system-probe"])

    assert result.exit_code == 0
    assert '"status": "success"' in result.stdout


def test_run_system_probe_command_returns_error_exit_code(monkeypatch) -> None:
    def fake_run_registered_job(**kwargs):
        return JobRunResult(
            run_id=2,
            module_id=1,
            module_name="system_core",
            job_name=kwargs["job_name"],
            trigger_source=kwargs["trigger_source"],
            account_id=kwargs.get("account_id"),
            status="error",
            error_message="boom",
            payload=None,
        )

    monkeypatch.setattr(cli_app_module, "run_registered_job", fake_run_registered_job)

    result = runner.invoke(cli, ["run-system-probe", "--fail"])

    assert result.exit_code == 1
    assert '"status": "error"' in result.stdout
