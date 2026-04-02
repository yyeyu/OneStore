"""Registered inbox sync jobs for Module 2 runtime integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.inbox import InboxService
from app.jobs.context import RunContext
from app.jobs.runner import JobRunner
from app.modules import ModuleAccessService


class InboxSyncJob:
    """Run one inbox sync for the account in the job context."""

    def __init__(self, *, service: InboxService | None = None):
        self._service = service or InboxService()

    def __call__(self, context: RunContext) -> dict[str, Any]:
        if context.account_id is None:
            raise RuntimeError("Inbox sync job requires account_id.")

        result = self._service.sync_account_inbox(context.account_id)
        return asdict(result)


class InboxSyncAllJob:
    """Fan out inbox sync across all runnable accounts for module2_inbox."""

    def __init__(
        self,
        *,
        runner: JobRunner | None = None,
        access_service: ModuleAccessService | None = None,
    ):
        self._runner = runner
        self._access_service = access_service

    def __call__(self, context: RunContext) -> dict[str, Any]:
        from app.jobs.registry import run_registered_jobs_for_accounts

        results = run_registered_jobs_for_accounts(
            job_name="inbox-sync",
            trigger_source=context.trigger_source,
            runner=self._runner,
            access_service=self._access_service,
        )
        return {
            "job_name": context.job_name,
            "module_name": context.module_name,
            "trigger_source": context.trigger_source,
            "account_count": len(results),
            "success_count": sum(1 for result in results if result.status == "success"),
            "error_count": sum(1 for result in results if result.status == "error"),
            "results": [result.model_dump(mode="json") for result in results],
        }


def build_inbox_sync_job(*, service: InboxService | None = None) -> InboxSyncJob:
    """Build one-account inbox sync job."""
    return InboxSyncJob(service=service)


def build_inbox_sync_all_job(
    *,
    runner: JobRunner | None = None,
    access_service: ModuleAccessService | None = None,
) -> InboxSyncAllJob:
    """Build fan-out inbox sync job."""
    return InboxSyncAllJob(runner=runner, access_service=access_service)
