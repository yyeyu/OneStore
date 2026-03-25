from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import app.core.smoke as smoke_module
from app.actions import ActionResult
from fastapi import FastAPI
from app.modules import (
    AccountMutationResult,
    AccountSummary,
    LocalBootstrapSummary,
    ModuleSettingMutationResult,
    ModuleSettingSummary,
)


def test_run_smoke_check(monkeypatch) -> None:
    application = FastAPI()

    class FakeSession:
        def __enter__(self) -> FakeSession:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, model, run_id):
            if str(run_id).endswith("0001"):
                return SimpleNamespace(
                    id=run_id,
                    details_json={
                        "events": [{"status": "success"}],
                        "lock": {"scope": "job-lock"},
                    },
                )
            return SimpleNamespace(
                id=run_id,
                request_payload={"target": "smoke-target"},
                result_payload={"mock_effect_applied": True},
                run_id=UUID("00000000-0000-0000-0000-000000000001"),
            )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "Avito AI Assistant", "environment": "test"}

    monkeypatch.setattr(smoke_module, "upgrade_database", lambda: None)
    monkeypatch.setattr(smoke_module, "check_database_connection", lambda: None)
    monkeypatch.setattr(smoke_module, "create_app", lambda: application)
    monkeypatch.setattr(
        smoke_module,
        "build_system_summary",
        lambda: {
            "status": "ok",
            "log_format": "text",
        },
    )
    monkeypatch.setattr(
        smoke_module,
        "run_scheduler_loop",
        lambda **kwargs: {
            "status": "ok",
            "registered_jobs": ["job:ping", "job:account-ping"],
            "mode": kwargs["mode"],
        },
    )
    monkeypatch.setattr(
        smoke_module,
        "ModuleOperationsService",
        lambda: SimpleNamespace(
            bootstrap_local=lambda **kwargs: LocalBootstrapSummary(
                account=AccountMutationResult(
                    created=True,
                    account=AccountSummary(
                        account_id=uuid4(),
                        account_code="smoke-local",
                        display_name="Smoke Local Account",
                        external_account_id=None,
                        is_active=True,
                    ),
                ),
                module_setting=ModuleSettingMutationResult(
                    created=True,
                    module_setting=ModuleSettingSummary(
                        setting_id=uuid4(),
                        account_id=uuid4(),
                        account_code="smoke-local",
                        module_name="module0",
                        is_enabled=True,
                        settings_json={},
                    ),
                ),
            )
        ),
    )
    monkeypatch.setattr(
        smoke_module,
        "run_registered_job",
        lambda **kwargs: SimpleNamespace(
            status="success",
            run_id="00000000-0000-0000-0000-000000000001",
            correlation_id="corr-1",
        ),
    )
    action_log_ids = iter(
        [
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003",
        ]
    )
    monkeypatch.setattr(
        smoke_module,
        "execute_demo_action",
        lambda **kwargs: ActionResult(
            action_log_id=next(action_log_ids),
            module_name="module0",
            action_name="demo_dispatch",
            account_id="00000000-0000-0000-0000-000000000004",
            run_id="00000000-0000-0000-0000-000000000001",
            correlation_id="corr-1",
            mode=kwargs["mode"],
            status="dry_run" if kwargs["mode"] == "dry_run" else "success",
            idempotency_key="key-1",
            duplicate=False,
            request_payload={"target": "smoke-target"},
            result_payload={
                "mock_effect_applied": kwargs["mode"] == "live",
            },
            error_message=None,
        ),
    )
    monkeypatch.setattr(
        smoke_module,
        "get_session_factory",
        lambda: lambda: FakeSession(),
    )

    summary = smoke_module.run_smoke_check()

    assert summary["status"] == "ok"
    assert summary["system"]["log_format"] == "text"
    assert summary["api_health"]["status"] == "ok"
    assert summary["scheduler"]["status"] == "ok"
    assert summary["bootstrap_account_code"] == "smoke-local"
    assert summary["bootstrap_module_enabled"] is True
    assert summary["job_status"] == "success"
    assert summary["job_recorded"] is True
    assert summary["action_dry_run_status"] == "dry_run"
    assert summary["action_live_status"] == "success"
    assert summary["action_dry_run_duplicate"] is False
    assert summary["action_live_duplicate"] is False
    assert summary["journals"]["module_run_has_events"] is True
    assert summary["journals"]["module_run_has_lock"] is True
    assert summary["journals"]["dry_action_has_request_payload"] is True
    assert summary["journals"]["dry_action_has_result_payload"] is True
    assert summary["journals"]["live_action_has_request_payload"] is True
    assert summary["journals"]["live_action_has_result_payload"] is True
    assert summary["journals"]["live_action_has_run_link"] is True
