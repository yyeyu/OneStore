"""Local smoke-check workflow for Module 0."""

from __future__ import annotations

from uuid import uuid4

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
    """Run compact end-to-end checks for the simplified runtime."""
    system_summary = build_system_summary()
    upgrade_database()
    check_database_connection()

    with TestClient(create_app()) as client:
        health_response = client.get("/health")
        health_response.raise_for_status()
        health_payload = health_response.json()

    scheduler_summary = run_scheduler_loop(interval_seconds=300, duration_seconds=0)

    operations_service = ModuleOperationsService()
    bootstrap_summary = operations_service.bootstrap_local(
        name="Smoke Local Account",
        client_id="smoke-local-client",
        client_secret="smoke-local-secret",
        module_name="module0",
    )
    job_result = run_registered_job(
        job_name="account-ping",
        trigger_source="manual",
        account_id=bootstrap_summary.account.account.id,
    )
    action_result = execute_demo_action(
        target="smoke-target",
        message=f"smoke:{uuid4().hex}",
        account_id=bootstrap_summary.account.account.id,
        run_id=job_result.run_id,
    )

    session_factory = get_session_factory()
    with session_factory() as session:
        run_record = session.get(ModuleRun, job_result.run_id)
        action_log = session.get(ActionLog, action_result.action_log_id)

    return {
        "status": "ok",
        "system": system_summary,
        "api_health": health_payload,
        "scheduler": scheduler_summary,
        "bootstrap_account_id": bootstrap_summary.account.account.id,
        "bootstrap_account_created": bootstrap_summary.account.created,
        "bootstrap_module_id": bootstrap_summary.module_setting.module_setting.module_id,
        "bootstrap_module_enabled": bootstrap_summary.module_setting.module_setting.is_enabled,
        "job_status": job_result.status,
        "job_run_id": job_result.run_id,
        "job_recorded": run_record is not None,
        "job_finished_at_present": bool(run_record and run_record.finished_at),
        "action_status": action_result.status,
        "action_log_id": action_result.action_log_id,
        "action_recorded": action_log is not None,
        "action_has_run_link": bool(action_log and action_log.run_id == job_result.run_id),
    }
