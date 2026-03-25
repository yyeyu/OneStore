from __future__ import annotations

import app.cli.app as cli_app_module

import pytest
from typer.testing import CliRunner

from app.jobs.registry import get_job_definition, list_job_definitions, run_registered_job
from app.jobs.runner import JobRunResult
from app.jobs.scheduler import build_scheduler
from app.main import cli
from app.modules import ModuleRunAccessError


runner = CliRunner()


class SpyRunner:
    def __init__(self):
        self.context = None
        self.job = None

    def run(self, *, context, module_id, job):
        self.context = context
        self.job = job
        return JobRunResult(
            run_id=1,
            module_id=module_id,
            module_name=context.module_name,
            job_name=context.job_name,
            trigger_source=context.trigger_source,
            account_id=context.account_id,
            status="success",
            error_message=None,
            payload={"message": "pong"},
        )


def test_job_registry_contains_ping_definition() -> None:
    definition = get_job_definition("ping")

    assert definition.name == "ping"
    assert definition.module_name == "module0"
    assert definition.default_interval_seconds == 30


def test_job_registry_contains_account_ping_definition() -> None:
    definition = get_job_definition("account-ping")

    assert definition.name == "account-ping"
    assert definition.requires_account is True


def test_run_registered_job_uses_provided_runner() -> None:
    spy_runner = SpyRunner()

    class FakeAccessService:
        def assert_job_can_run(self, **kwargs):
            class _Module:
                id = 1

            class _Decision:
                module = _Module()

            return _Decision()

    result = run_registered_job(
        job_name="ping",
        trigger_source="manual",
        runner=spy_runner,
        access_service=FakeAccessService(),
    )

    assert result.status == "success"
    assert spy_runner.context.job_name == "ping"
    assert spy_runner.context.trigger_source == "manual"
    assert spy_runner.job(spy_runner.context)["message"] == "pong"


def test_build_scheduler_registers_jobs_with_scheduler_source() -> None:
    scheduler = build_scheduler(interval_seconds=5)
    jobs = scheduler.get_jobs()
    job_names = {job.kwargs["job_name"] for job in jobs}

    assert len(jobs) == len(list_job_definitions())
    assert job_names == {"ping", "account-ping"}
    assert all(job.kwargs["trigger_source"] == "scheduler" for job in jobs)


def test_run_registered_job_requires_account_for_account_jobs() -> None:
    class FakeAccessService:
        def assert_job_can_run(self, **kwargs):
            raise ModuleRunAccessError(
                "account_required",
                "Job 'account-ping' requires account_id.",
            )

    with pytest.raises(ModuleRunAccessError, match="requires account_id"):
        run_registered_job(
            job_name="account-ping",
            trigger_source="manual",
            access_service=FakeAccessService(),
        )


def test_run_job_command(monkeypatch) -> None:
    def fake_run_registered_job(**kwargs):
        return JobRunResult(
            run_id=1,
            module_id=1,
            module_name="module0",
            job_name=kwargs["job_name"],
            trigger_source=kwargs["trigger_source"],
            account_id=kwargs.get("account_id"),
            status="success",
            error_message=None,
            payload={"message": "pong"},
        )

    monkeypatch.setattr(cli_app_module, "run_registered_job", fake_run_registered_job)

    result = runner.invoke(cli, ["run-job", "ping"])

    assert result.exit_code == 0
    assert '"job_name": "ping"' in result.stdout
    assert '"status": "success"' in result.stdout


def test_run_job_command_returns_account_access_error(monkeypatch) -> None:
    def fake_run_registered_job(**kwargs):
        raise ModuleRunAccessError(
            "account_required",
            "Job 'account-ping' requires account_id.",
        )

    monkeypatch.setattr(cli_app_module, "run_registered_job", fake_run_registered_job)

    result = runner.invoke(cli, ["run-job", "account-ping"])

    assert result.exit_code == 1
    assert '"error_code": "account_required"' in result.stdout


def test_run_scheduler_command(monkeypatch) -> None:
    def fake_run_scheduler_loop(**kwargs):
        return {
            "status": "ok",
            "registered_jobs": ["job:ping"],
            "interval_seconds": kwargs["interval_seconds"],
            "duration_seconds": kwargs["duration_seconds"],
        }

    monkeypatch.setattr(cli_app_module, "run_scheduler_loop", fake_run_scheduler_loop)

    result = runner.invoke(
        cli,
        ["run-scheduler", "--interval-seconds", "1", "--duration-seconds", "3"],
    )

    assert result.exit_code == 0
    assert '"registered_jobs": [' in result.stdout
    assert '"status": "ok"' in result.stdout
