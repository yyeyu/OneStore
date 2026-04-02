from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import app.core.smoke as smoke_module
from app.actions import ActionResult


def test_run_smoke_check_covers_module2_inbox_path(monkeypatch) -> None:
    monkeypatch.setattr(smoke_module, "upgrade_database", lambda: None)
    monkeypatch.setattr(smoke_module, "check_database_connection", lambda: None)
    monkeypatch.setattr(
        smoke_module,
        "build_system_summary",
        lambda: {"status": "ok", "log_format": "text"},
    )
    monkeypatch.setattr(
        smoke_module,
        "run_scheduler_loop",
        lambda **kwargs: {
            "status": "ok",
            "registered_jobs": ["system-probe", "inbox-sync-all", "inbox-health-check"],
        },
    )
    monkeypatch.setattr(
        smoke_module,
        "ModuleOperationsService",
        lambda: SimpleNamespace(
            ensure_default_modules=lambda module_names: (
                SimpleNamespace(id=1, name="system_core"),
                SimpleNamespace(id=2, name="module2_inbox"),
            ),
            bootstrap_local=lambda **kwargs: SimpleNamespace(
                account=SimpleNamespace(
                    created=True,
                    account=SimpleNamespace(id=101, avito_user_id="smoke-avito-user"),
                ),
                module_setting=SimpleNamespace(
                    module_setting=SimpleNamespace(module_id=1, is_enabled=True),
                ),
            ),
            set_module_state=lambda **kwargs: SimpleNamespace(
                module_setting=SimpleNamespace(is_enabled=True),
            ),
        ),
    )

    def fake_run_registered_job(**kwargs):
        if kwargs["job_name"] == "account-system-probe":
            return SimpleNamespace(status="success", run_id=1, payload={"status": "success"})
        if kwargs["job_name"] == "inbox-sync":
            return SimpleNamespace(
                status="success",
                run_id=2,
                payload={
                    "status": "success",
                    "account_id": 101,
                    "chats_synced": 1,
                    "messages_synced": 2,
                    "clients_synced": 1,
                    "listings_synced": 1,
                },
            )
        raise AssertionError(f"Unexpected job: {kwargs['job_name']}")

    monkeypatch.setattr(smoke_module, "run_registered_job", fake_run_registered_job)
    monkeypatch.setattr(
        smoke_module,
        "execute_probe_action",
        lambda **kwargs: ActionResult(
            action_log_id=3,
            action_name="probe_dispatch",
            account_id=101,
            run_id=1,
            status="success",
            error_message=None,
            output={"delivery_state": "probe_dispatched"},
        ),
    )
    monkeypatch.setattr(
        smoke_module,
        "build_smoke_inbox_service",
        lambda: object(),
    )
    monkeypatch.setattr(
        smoke_module,
        "load_smoke_database_state",
        lambda **kwargs: {
            "job_recorded": True,
            "job_finished_at_present": True,
            "inbox_job_recorded": True,
            "inbox_job_finished_at_present": True,
            "action_recorded": True,
            "action_has_run_link": True,
            "chat_count": 1,
            "message_count": 2,
            "client_count": 1,
            "listing_count": 1,
            "chat_id": 777,
            "external_chat_id": "smoke-chat-1",
            "client_name": "Smoke Buyer",
            "listing_title": "Mazda 3 2008",
        },
    )
    monkeypatch.setattr(
        smoke_module,
        "collect_smoke_http_surface",
        lambda *args, **kwargs: {
            "api": {
                "chat_count": 1,
                "message_count": 2,
                "client_count": 1,
                "listing_count": 1,
                "dashboard_total_chats": 1,
                "dashboard_total_messages": 2,
                "chat_details_message_count": 2,
            },
            "admin": {
                "dashboard_ok": True,
                "accounts_ok": True,
                "chats_ok": True,
                "chat_details_ok": True,
                "messages_ok": True,
                "clients_ok": True,
                "listings_ok": True,
            },
        },
    )

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, path: str, params: dict[str, object] | None = None) -> FakeResponse:
            assert path == "/health"
            assert params is None
            return FakeResponse(
                {"status": "ok", "service": "OneStore", "environment": "test"}
            )

    monkeypatch.setattr(smoke_module, "create_app", lambda: object())
    monkeypatch.setattr(smoke_module, "TestClient", lambda app: FakeClient())

    summary = smoke_module.run_smoke_check()

    assert summary["status"] == "ok"
    assert summary["system"]["log_format"] == "text"
    assert summary["module2_inbox_present"] is True
    assert summary["module2_inbox_enabled"] is True
    assert summary["inbox_job_status"] == "success"
    assert summary["inbox_payload"]["messages_synced"] == 2
    assert summary["inbox_counts"]["chats"] == 1
    assert summary["http_surface"]["api"]["chat_count"] == 1
    assert summary["http_surface"]["admin"]["chat_details_ok"] is True


def test_load_smoke_database_state_reads_persisted_counts() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base
    from app.db.models import (
        ActionLog,
        AvitoAccount,
        AvitoChat,
        AvitoClient,
        AvitoListingRef,
        AvitoMessage,
        Module,
        ModuleAccountSetting,
        ModuleRun,
    )

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    local_session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )

    try:
        with local_session_factory() as session:
            module = Module(name="module2_inbox")
            account = AvitoAccount(
                name="Smoke Account",
                client_id="smoke-client",
                client_secret="smoke-secret",
                avito_user_id="smoke-user",
                is_active=True,
                last_inbox_sync_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
                last_inbox_sync_status="success",
            )
            session.add_all([module, account])
            session.flush()

            session.add(
                ModuleAccountSetting(
                    account_id=account.id,
                    module_id=module.id,
                    is_enabled=True,
                )
            )
            system_run = ModuleRun(
                account_id=account.id,
                module_id=module.id,
                job_name="account-system-probe",
                trigger_source="manual",
                status="success",
                finished_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
            )
            inbox_run = ModuleRun(
                account_id=account.id,
                module_id=module.id,
                job_name="inbox-sync",
                trigger_source="manual",
                status="success",
                finished_at=datetime(2026, 4, 2, 12, 1, tzinfo=UTC),
            )
            session.add_all([system_run, inbox_run])
            session.flush()

            client = AvitoClient(
                account_id=account.id,
                external_user_id="2002",
                display_name="Smoke Buyer",
            )
            listing = AvitoListingRef(
                account_id=account.id,
                external_item_id="1768287444",
                title="Mazda 3 2008",
            )
            session.add_all([client, listing])
            session.flush()

            chat = AvitoChat(
                account_id=account.id,
                external_chat_id="smoke-chat-1",
                chat_type="u2i",
                client_id=client.id,
                listing_id=listing.id,
                external_created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                external_updated_at=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
            )
            session.add(chat)
            session.flush()

            session.add_all(
                [
                    AvitoMessage(
                        account_id=account.id,
                        chat_id=chat.id,
                        external_message_id="smoke-message-1",
                        direction="in",
                        message_type="text",
                        content_json={"text": "Hello"},
                        external_created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                    ),
                    AvitoMessage(
                        account_id=account.id,
                        chat_id=chat.id,
                        external_message_id="smoke-message-2",
                        direction="out",
                        message_type="text",
                        content_json={"text": "Hi"},
                        external_created_at=datetime(2026, 4, 2, 10, 1, tzinfo=UTC),
                    ),
                ]
            )
            action_log = ActionLog(
                account_id=account.id,
                run_id=system_run.id,
                action_name="probe_dispatch",
                status="success",
            )
            session.add(action_log)
            session.commit()

        state = smoke_module.load_smoke_database_state(
            account_id=account.id,
            system_job_run_id=system_run.id,
            inbox_job_run_id=inbox_run.id,
            action_log_id=action_log.id,
            session_factory=local_session_factory,
        )

        assert state["job_recorded"] is True
        assert state["inbox_job_recorded"] is True
        assert state["action_has_run_link"] is True
        assert state["chat_count"] == 1
        assert state["message_count"] == 2
        assert state["client_count"] == 1
        assert state["listing_count"] == 1
        assert state["external_chat_id"] == "smoke-chat-1"
        assert state["client_name"] == "Smoke Buyer"
        assert state["listing_title"] == "Mazda 3 2008"
    finally:
        engine.dispose()
