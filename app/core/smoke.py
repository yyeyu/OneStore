"""Local smoke-check workflow for Module 0."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.actions import execute_demo_action
from app.api.app import create_app
from app.core.diagnostics import build_system_summary
from app.db import ModuleRun, get_session_factory
from app.db.models import ActionLog
from app.db.migrations import upgrade_database
from app.db.session import check_database_connection
from app.jobs import run_registered_job, run_scheduler_loop
from app.modules import ModuleOperationsService


def run_smoke_check() -> dict[str, object]:
    """Run a compact end-to-end local verification for Module 0."""
    system_summary = build_system_summary()
    upgrade_database()
    check_database_connection()

    with TestClient(create_app()) as client:
        health_response = client.get("/health")
        health_response.raise_for_status()
        health_payload = health_response.json()

    scheduler_summary = run_scheduler_loop(
        mode="dry_run",
        interval_seconds=300,
        duration_seconds=0,
    )

    operations_service = ModuleOperationsService()
    bootstrap_summary = operations_service.bootstrap_local(
        account_code="smoke-local",
        display_name="Smoke Local Account",
        module_name="module0",
    )
    job_result = run_registered_job(
        job_name="account-ping",
        trigger_source="manual",
        mode="dry_run",
        account_id=bootstrap_summary.account.account.account_id,
    )
    dry_action_result = execute_demo_action(
        target="smoke-target",
        message=f"smoke:{uuid4().hex}",
        mode="dry_run",
        account_id=bootstrap_summary.account.account.account_id,
        run_id=UUID(job_result.run_id),
        correlation_id=job_result.correlation_id,
    )
    live_action_result = execute_demo_action(
        target="smoke-target-live",
        message=f"smoke-live:{uuid4().hex}",
        mode="live",
        account_id=bootstrap_summary.account.account.account_id,
        run_id=UUID(job_result.run_id),
        correlation_id=job_result.correlation_id,
    )
    session_factory = get_session_factory()
    with session_factory() as session:
        run_record = session.get(ModuleRun, UUID(job_result.run_id))
        dry_action_log = session.get(ActionLog, UUID(dry_action_result.action_log_id))
        live_action_log = session.get(ActionLog, UUID(live_action_result.action_log_id))

    return {
        "status": "ok",
        "system": system_summary,
        "api_health": health_payload,
        "scheduler": scheduler_summary,
        "account_identifier": "account_code",
        "bootstrap_account_code": bootstrap_summary.account.account.account_code,
        "bootstrap_account_id": str(bootstrap_summary.account.account.account_id),
        "bootstrap_account_created": bootstrap_summary.account.created,
        "bootstrap_module_enabled": (
            bootstrap_summary.module_setting.module_setting.is_enabled
        ),
        "job_status": job_result.status,
        "job_run_id": job_result.run_id,
        "job_recorded": run_record is not None,
        "action_dry_run_status": dry_action_result.status,
        "action_dry_run_log_id": dry_action_result.action_log_id,
        "action_dry_run_duplicate": dry_action_result.duplicate,
        "action_live_status": live_action_result.status,
        "action_live_log_id": live_action_result.action_log_id,
        "action_live_duplicate": live_action_result.duplicate,
        "journals": {
            "module_run_has_events": bool(
                run_record and (run_record.details_json or {}).get("events")
            ),
            "module_run_has_lock": bool(
                run_record and (run_record.details_json or {}).get("lock")
            ),
            "dry_action_has_request_payload": bool(
                dry_action_log and dry_action_log.request_payload
            ),
            "dry_action_has_result_payload": bool(
                dry_action_log and dry_action_log.result_payload
            ),
            "live_action_has_request_payload": bool(
                live_action_log and live_action_log.request_payload
            ),
            "live_action_has_result_payload": bool(
                live_action_log and live_action_log.result_payload
            ),
            "live_action_has_run_link": bool(
                live_action_log and live_action_log.run_id == UUID(job_result.run_id)
            ),
        },
    }
