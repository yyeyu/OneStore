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

    def run(self, context, job):
        self.context = context
        self.job = job
        return JobRunResult(
            run_id="spy-run",
            correlation_id=context.correlation_id,
            module_name=context.module_name,
            job_name=context.job_name,
            trigger_source=context.trigger_source,
            mode=context.mode,
            account_id=None,
            status="success",
            details={"events": []},
            error_message=None,
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

    result = run_registered_job(
        job_name="ping",
        trigger_source="manual",
        mode="dry_run",
        runner=spy_runner,
    )

    assert result.status == "success"
    assert spy_runner.context.job_name == "ping"
    assert spy_runner.context.trigger_source == "manual"
    assert spy_runner.job(spy_runner.context)["message"] == "pong"


def test_build_scheduler_registers_jobs_with_scheduler_source() -> None:
    scheduler = build_scheduler(mode="dry_run", interval_seconds=5)
    jobs = scheduler.get_jobs()
    job_names = {job.kwargs["job_name"] for job in jobs}

    assert len(jobs) == len(list_job_definitions())
    assert job_names == {"ping", "account-ping"}
    assert all(job.kwargs["trigger_source"] == "scheduler" for job in jobs)
    assert all(job.kwargs["mode"] == "dry_run" for job in jobs)


def test_run_registered_job_requires_account_for_account_jobs() -> None:
    with pytest.raises(ModuleRunAccessError, match="requires account_id"):
        run_registered_job(
            job_name="account-ping",
            trigger_source="manual",
            mode="dry_run",
        )


def test_run_job_command(monkeypatch) -> None:
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


def test_run_job_command_returns_locked_exit_code(monkeypatch) -> None:
    def fake_run_registered_job(**kwargs):
        return JobRunResult(
            run_id="run-locked",
            correlation_id="corr-locked",
            module_name="module0",
            job_name=kwargs["job_name"],
            trigger_source=kwargs["trigger_source"],
            mode=kwargs["mode"],
            account_id=None,
            status="locked",
            details={"events": [], "lock": {"reason": "already_running"}},
            error_message="Job execution skipped because another run already holds the lock.",
        )

    monkeypatch.setattr(cli_app_module, "run_registered_job", fake_run_registered_job)

    result = runner.invoke(cli, ["run-job", "ping"])

    assert result.exit_code == 1
    assert '"status": "locked"' in result.stdout


def test_run_scheduler_command(monkeypatch) -> None:
    def fake_run_scheduler_loop(**kwargs):
        return {
            "status": "ok",
            "registered_jobs": ["job:ping"],
            "mode": kwargs["mode"],
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
