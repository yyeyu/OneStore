from __future__ import annotations

from types import SimpleNamespace

import app.core.smoke as smoke_module
from app.actions import ActionResult
from fastapi import FastAPI


def test_run_smoke_check(monkeypatch) -> None:
    application = FastAPI()

    class FakeSession:
        def __enter__(self) -> FakeSession:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, model, row_id):
            if str(model.__name__) == "ModuleRun":
                return SimpleNamespace(id=row_id, finished_at="2026-03-25T00:00:00Z")
            return SimpleNamespace(id=row_id, run_id=1)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "Avito AI Assistant", "environment": "test"}

    monkeypatch.setattr(smoke_module, "upgrade_database", lambda: None)
    monkeypatch.setattr(smoke_module, "check_database_connection", lambda: None)
    monkeypatch.setattr(smoke_module, "create_app", lambda: application)
    monkeypatch.setattr(
        smoke_module,
        "build_system_summary",
        lambda: {"status": "ok", "log_format": "text"},
    )
    monkeypatch.setattr(
        smoke_module,
        "run_scheduler_loop",
        lambda **kwargs: {"status": "ok", "registered_jobs": ["job:ping", "job:account-ping"]},
    )
    monkeypatch.setattr(
        smoke_module,
        "ModuleOperationsService",
        lambda: SimpleNamespace(
            bootstrap_local=lambda **kwargs: SimpleNamespace(
                account=SimpleNamespace(
                    created=True,
                    account=SimpleNamespace(id=101),
                ),
                module_setting=SimpleNamespace(
                    module_setting=SimpleNamespace(module_id=1, is_enabled=True),
                ),
            )
        ),
    )
    monkeypatch.setattr(
        smoke_module,
        "run_registered_job",
        lambda **kwargs: SimpleNamespace(status="success", run_id=1),
    )
    monkeypatch.setattr(
        smoke_module,
        "execute_demo_action",
        lambda **kwargs: ActionResult(
            action_log_id=2,
            action_name="demo_dispatch",
            account_id=101,
            run_id=1,
            status="success",
            error_message=None,
            output={"delivery_state": "mock_dispatched"},
        ),
    )
    monkeypatch.setattr(smoke_module, "get_session_factory", lambda: lambda: FakeSession())

    summary = smoke_module.run_smoke_check()

    assert summary["status"] == "ok"
    assert summary["system"]["log_format"] == "text"
    assert summary["api_health"]["status"] == "ok"
    assert summary["scheduler"]["status"] == "ok"
    assert summary["bootstrap_account_id"] == 101
    assert summary["bootstrap_module_id"] == 1
    assert summary["bootstrap_module_enabled"] is True
    assert summary["job_status"] == "success"
    assert summary["job_recorded"] is True
    assert summary["job_finished_at_present"] is True
    assert summary["action_status"] == "success"
    assert summary["action_recorded"] is True
    assert summary["action_has_run_link"] is True
