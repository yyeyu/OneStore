from __future__ import annotations

from datetime import UTC, datetime, timedelta

import app.jobs.registry as registry_module
import pytest

from app.inbox.schemas import DashboardSummaryRead, SyncAccountSummary
from app.inbox.sync import InboxSyncResult
from app.jobs.context import RunContext
from app.jobs.inbox_health import build_inbox_health_check_job
from app.jobs.inbox_sync import build_inbox_sync_all_job, build_inbox_sync_job
from app.jobs.runner import JobRunResult


def test_inbox_sync_job_calls_service_for_context_account() -> None:
    class FakeInboxService:
        def sync_account_inbox(self, account_id: int) -> InboxSyncResult:
            assert account_id == 101
            return InboxSyncResult(
                account_id=101,
                account_name="Store A",
                synced_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
                status="success",
                last_error=None,
                chats_synced=2,
                messages_synced=5,
                clients_synced=1,
                listings_synced=1,
            )

    job = build_inbox_sync_job(service=FakeInboxService())
    payload = job(
        RunContext(
            module_name="module2_inbox",
            job_name="inbox-sync",
            trigger_source="manual",
            account_id=101,
        )
    )

    assert payload["account_id"] == 101
    assert payload["status"] == "success"
    assert payload["messages_synced"] == 5


def test_inbox_sync_all_job_fans_out_to_registered_account_job(monkeypatch) -> None:
    def fake_run_registered_jobs_for_accounts(**kwargs):
        assert kwargs["job_name"] == "inbox-sync"
        assert kwargs["trigger_source"] == "scheduler"
        return (
            JobRunResult(
                run_id=1,
                module_id=2,
                module_name="module2_inbox",
                job_name="inbox-sync",
                trigger_source="scheduler",
                account_id=101,
                status="success",
                error_message=None,
                payload={"status": "success"},
            ),
            JobRunResult(
                run_id=2,
                module_id=2,
                module_name="module2_inbox",
                job_name="inbox-sync",
                trigger_source="scheduler",
                account_id=102,
                status="error",
                error_message="boom",
                payload=None,
            ),
        )

    monkeypatch.setattr(
        registry_module,
        "run_registered_jobs_for_accounts",
        fake_run_registered_jobs_for_accounts,
    )

    job = build_inbox_sync_all_job()
    payload = job(
        RunContext(
            module_name="module2_inbox",
            job_name="inbox-sync-all",
            trigger_source="scheduler",
        )
    )

    assert payload["account_count"] == 2
    assert payload["success_count"] == 1
    assert payload["error_count"] == 1


def test_inbox_health_check_job_returns_payload_for_healthy_accounts() -> None:
    class FakeAccessService:
        def list_runnable_account_ids(self, **kwargs):
            assert kwargs["module_name"] == "module2_inbox"
            return (101,)

    class FakeInboxService:
        def get_dashboard_summary(self) -> DashboardSummaryRead:
            return DashboardSummaryRead(
                total_accounts=1,
                active_accounts=1,
                total_chats=2,
                total_messages=5,
                total_clients=1,
                total_listings=1,
                accounts=(
                    SyncAccountSummary(
                        account_id=101,
                        account_name="Store A",
                        avito_user_id="1001",
                        is_active=True,
                        last_inbox_sync_at=datetime.now(UTC),
                        last_inbox_sync_status="success",
                        last_inbox_error=None,
                        chat_count=2,
                        message_count=5,
                    ),
                ),
            )

    job = build_inbox_health_check_job(
        service=FakeInboxService(),
        access_service=FakeAccessService(),
        stale_after_hours=24,
    )
    payload = job(
        RunContext(
            module_name="module2_inbox",
            job_name="inbox-health-check",
            trigger_source="scheduler",
        )
    )

    assert payload["checked_account_count"] == 1
    assert payload["accounts_without_sync"] == []
    assert payload["accounts_with_errors"] == []
    assert payload["stale_accounts"] == []


def test_inbox_health_check_job_raises_for_stale_or_broken_accounts() -> None:
    class FakeAccessService:
        def list_runnable_account_ids(self, **kwargs):
            return (101, 102)

    class FakeInboxService:
        def get_dashboard_summary(self) -> DashboardSummaryRead:
            return DashboardSummaryRead(
                total_accounts=2,
                active_accounts=2,
                total_chats=2,
                total_messages=5,
                total_clients=1,
                total_listings=1,
                accounts=(
                    SyncAccountSummary(
                        account_id=101,
                        account_name="Store A",
                        avito_user_id="1001",
                        is_active=True,
                        last_inbox_sync_at=datetime.now(UTC) - timedelta(hours=30),
                        last_inbox_sync_status="success",
                        last_inbox_error=None,
                        chat_count=2,
                        message_count=5,
                    ),
                    SyncAccountSummary(
                        account_id=102,
                        account_name="Store B",
                        avito_user_id="1002",
                        is_active=True,
                        last_inbox_sync_at=None,
                        last_inbox_sync_status="error",
                        last_inbox_error="boom",
                        chat_count=0,
                        message_count=0,
                    ),
                ),
            )

    job = build_inbox_health_check_job(
        service=FakeInboxService(),
        access_service=FakeAccessService(),
        stale_after_hours=24,
    )

    with pytest.raises(RuntimeError, match="Inbox health check failed"):
        job(
            RunContext(
                module_name="module2_inbox",
                job_name="inbox-health-check",
                trigger_source="scheduler",
            )
        )
