"""Registry for demonstration jobs and shared execution entrypoints."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

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
    logical_scope: str = "default"


JOB_REGISTRY: dict[str, JobDefinition] = {
    "ping": JobDefinition(
        name="ping",
        module_name="module0",
        description="Demonstration ping job for JobRunner and scheduler checks.",
        default_interval_seconds=30,
        factory=build_ping_job,
    ),
    "account-ping": JobDefinition(
        name="account-ping",
        module_name="module0",
        description="Demonstration ping job that requires an enabled account/module.",
        default_interval_seconds=30,
        factory=build_ping_job,
        requires_account=True,
    ),
}


def get_job_definition(job_name: str) -> JobDefinition:
    """Return a registered job definition or raise a helpful error."""
    try:
        return JOB_REGISTRY[job_name]
    except KeyError as exc:
        available = ", ".join(sorted(JOB_REGISTRY))
        raise ValueError(f"Unknown job '{job_name}'. Available jobs: {available}") from exc


def list_job_definitions() -> tuple[JobDefinition, ...]:
    """Return all registered jobs in a stable order."""
    return tuple(JOB_REGISTRY[name] for name in sorted(JOB_REGISTRY))


def run_registered_job(
    *,
    job_name: str,
    trigger_source: str,
    mode: str,
    account_id: UUID | None = None,
    correlation_id: str | None = None,
    logical_scope: str | None = None,
    runner: JobRunner | None = None,
    access_service: ModuleAccessService | None = None,
    **job_options: Any,
) -> JobRunResult:
    """Create context, build a job and execute it through the shared JobRunner."""
    definition = get_job_definition(job_name)
    active_access_service = access_service or ModuleAccessService()
    active_access_service.assert_job_can_run(
        module_name=definition.module_name,
        job_name=definition.name,
        account_id=account_id,
        requires_account=definition.requires_account,
    )
    context_kwargs = {
        "module_name": definition.module_name,
        "job_name": definition.name,
        "trigger_source": trigger_source,
        "mode": mode,
        "account_id": account_id,
        "logical_scope": logical_scope or definition.logical_scope,
    }
    if correlation_id is not None:
        context_kwargs["correlation_id"] = correlation_id

    context = RunContext(**context_kwargs)
    active_runner = runner or JobRunner()
    job = definition.factory(**job_options)
    return active_runner.run(context=context, job=job)


def run_registered_jobs_for_accounts(
    *,
    job_name: str,
    trigger_source: str,
    mode: str,
    runner: JobRunner | None = None,
    access_service: ModuleAccessService | None = None,
    logical_scope: str | None = None,
    **job_options: Any,
) -> tuple[JobRunResult, ...]:
    """Run a job once or fan it out across all eligible accounts."""
    definition = get_job_definition(job_name)
    active_access_service = access_service or ModuleAccessService()

    if not definition.requires_account:
        return (
            run_registered_job(
                job_name=job_name,
                trigger_source=trigger_source,
                mode=mode,
                runner=runner,
                access_service=active_access_service,
                logical_scope=logical_scope,
                **job_options,
            ),
        )

    results: list[JobRunResult] = []
    account_ids = active_access_service.list_runnable_account_ids(
        module_name=definition.module_name,
        job_name=definition.name,
    )
    for account_id in account_ids:
        results.append(
            run_registered_job(
                job_name=job_name,
                trigger_source=trigger_source,
                mode=mode,
                account_id=account_id,
                runner=runner,
                access_service=active_access_service,
                logical_scope=logical_scope,
                **job_options,
            )
        )

    return tuple(results)
