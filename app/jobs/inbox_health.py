"""Health-check job for Module 2 inbox runtime state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.inbox import InboxService
from app.jobs.context import RunContext
from app.modules import ModuleAccessService


class InboxHealthCheckJob:
    """Validate recent inbox sync state for enabled module2_inbox accounts."""

    def __init__(
        self,
        *,
        service: InboxService | None = None,
        access_service: ModuleAccessService | None = None,
        stale_after_hours: int = 24,
    ):
        self._service = service or InboxService()
        self._access_service = access_service or ModuleAccessService()
        self._stale_after_hours = stale_after_hours

    def __call__(self, context: RunContext) -> dict[str, Any]:
        runnable_account_ids = set(
            self._access_service.list_runnable_account_ids(
                module_name="module2_inbox",
                job_name=context.job_name,
            )
        )
        dashboard = self._service.get_dashboard_summary()
        relevant_accounts = tuple(
            account
            for account in dashboard.accounts
            if account.account_id in runnable_account_ids
        )
        threshold = datetime.now(UTC) - timedelta(hours=self._stale_after_hours)

        accounts_without_sync: list[int] = []
        accounts_with_errors: list[int] = []
        stale_accounts: list[int] = []

        for account in relevant_accounts:
            if account.last_inbox_sync_at is None:
                accounts_without_sync.append(account.account_id)
                continue
            if account.last_inbox_sync_status == "error" or account.last_inbox_error:
                accounts_with_errors.append(account.account_id)
            if _coerce_utc(account.last_inbox_sync_at) < threshold:
                stale_accounts.append(account.account_id)

        payload = {
            "job_name": context.job_name,
            "module_name": context.module_name,
            "trigger_source": context.trigger_source,
            "checked_account_count": len(relevant_accounts),
            "stale_after_hours": self._stale_after_hours,
            "accounts_without_sync": accounts_without_sync,
            "accounts_with_errors": accounts_with_errors,
            "stale_accounts": stale_accounts,
        }

        if accounts_without_sync or accounts_with_errors or stale_accounts:
            raise RuntimeError(
                (
                    "Inbox health check failed: "
                    f"missing_sync={len(accounts_without_sync)}, "
                    f"errors={len(accounts_with_errors)}, "
                    f"stale={len(stale_accounts)}."
                )
            )
        return payload


def build_inbox_health_check_job(
    *,
    service: InboxService | None = None,
    access_service: ModuleAccessService | None = None,
    stale_after_hours: int = 24,
) -> InboxHealthCheckJob:
    """Build inbox health-check job."""
    return InboxHealthCheckJob(
        service=service,
        access_service=access_service,
        stale_after_hours=stale_after_hours,
    )


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
