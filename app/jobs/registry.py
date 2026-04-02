"""Registry for platform jobs and shared execution entrypoints."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.jobs.context import RunContext
from app.jobs.inbox_health import build_inbox_health_check_job
from app.jobs.inbox_sync import build_inbox_sync_all_job, build_inbox_sync_job
from app.jobs.system_probe import build_system_probe_job
from app.jobs.runner import JobRunResult, JobRunner
from app.modules import ModuleAccessService

JobFactory = Callable[..., Callable[[RunContext], dict[str, Any] | None]]


@dataclass(frozen=True)
class JobDefinition:
    """Immutable registry entry for a runnable job."""

    name: str
    module_name: str
    description: str
    default_interval_seconds: int
    factory: JobFactory
    requires_account: bool = False
    scheduler_enabled: bool = True


JOB_REGISTRY: dict[str, JobDefinition] = {
    "system-probe": JobDefinition(
        name="system-probe",
        module_name="system_core",
        description="Temporary platform probe job for JobRunner and scheduler checks.",
        default_interval_seconds=30,
        factory=build_system_probe_job,
        requires_account=False,
        scheduler_enabled=True,
    ),
    "account-system-probe": JobDefinition(
        name="account-system-probe",
        module_name="system_core",
        description="Temporary probe job that requires an enabled account/module pair.",
        default_interval_seconds=30,
        factory=build_system_probe_job,
        requires_account=True,
        scheduler_enabled=False,
    ),
    "inbox-sync": JobDefinition(
        name="inbox-sync",
        module_name="module2_inbox",
        description="Sync one Avito inbox for one enabled account.",
        default_interval_seconds=300,
        factory=build_inbox_sync_job,
        requires_account=True,
        scheduler_enabled=False,
    ),
    "inbox-sync-all": JobDefinition(
        name="inbox-sync-all",
        module_name="module2_inbox",
        description="Fan out inbox sync across all active accounts with module2_inbox enabled.",
        default_interval_seconds=300,
        factory=build_inbox_sync_all_job,
        requires_account=False,
        scheduler_enabled=True,
    ),
    "inbox-health-check": JobDefinition(
        name="inbox-health-check",
        module_name="module2_inbox",
        description="Check last inbox sync timestamp, error state, and sync lag.",
        default_interval_seconds=600,
        factory=build_inbox_health_check_job,
        requires_account=False,
        scheduler_enabled=True,
    ),
}


def get_job_definition(job_name: str) -> JobDefinition:
    """Return a registered job definition."""
    try:
        return JOB_REGISTRY[job_name]
    except KeyError as exc:
        available = ", ".join(sorted(JOB_REGISTRY))
        raise ValueError(f"Unknown job '{job_name}'. Available jobs: {available}") from exc


def list_job_definitions() -> tuple[JobDefinition, ...]:
    """Return all registered jobs in stable order."""
    return tuple(JOB_REGISTRY[name] for name in sorted(JOB_REGISTRY))


def run_registered_job(
    *,
    job_name: str,
    trigger_source: str,
    account_id: int | None = None,
    runner: JobRunner | None = None,
    access_service: ModuleAccessService | None = None,
    **job_options: Any,
) -> JobRunResult:
    """Build context and execute a registered job."""
    definition = get_job_definition(job_name)
    active_access_service = access_service or ModuleAccessService()
    decision = active_access_service.assert_job_can_run(
        module_name=definition.module_name,
        job_name=definition.name,
        account_id=account_id,
        requires_account=definition.requires_account,
    )

    context = RunContext(
        module_name=definition.module_name,
        job_name=definition.name,
        trigger_source=trigger_source,
        account_id=account_id,
    )
    active_runner = runner or JobRunner()
    job = definition.factory(**job_options)
    return active_runner.run(context=context, module_id=decision.module.id, job=job)


def run_registered_jobs_for_accounts(
    *,
    job_name: str,
    trigger_source: str,
    runner: JobRunner | None = None,
    access_service: ModuleAccessService | None = None,
    **job_options: Any,
) -> tuple[JobRunResult, ...]:
    """Run one job globally or fan out across account ids."""
    definition = get_job_definition(job_name)
    active_access_service = access_service or ModuleAccessService()

    if not definition.requires_account:
        return (
            run_registered_job(
                job_name=job_name,
                trigger_source=trigger_source,
                runner=runner,
                access_service=active_access_service,
                **job_options,
            ),
        )

    account_ids = active_access_service.list_runnable_account_ids(
        module_name=definition.module_name,
        job_name=definition.name,
    )
    results: list[JobRunResult] = []
    for account_id in account_ids:
        results.append(
            run_registered_job(
                job_name=job_name,
                trigger_source=trigger_source,
                account_id=account_id,
                runner=runner,
                access_service=active_access_service,
                **job_options,
            )
        )
    return tuple(results)
