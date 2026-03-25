"""Registry for demo jobs and shared execution entrypoints."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.jobs.context import RunContext
from app.jobs.ping import build_ping_job
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


JOB_REGISTRY: dict[str, JobDefinition] = {
    "ping": JobDefinition(
        name="ping",
        module_name="module0",
        description="Demonstration ping job for JobRunner and scheduler checks.",
        default_interval_seconds=30,
        factory=build_ping_job,
        requires_account=False,
    ),
    "account-ping": JobDefinition(
        name="account-ping",
        module_name="module0",
        description="Ping job that requires an enabled account/module pair.",
        default_interval_seconds=30,
        factory=build_ping_job,
        requires_account=True,
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
