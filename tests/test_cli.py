import json
from datetime import UTC, datetime

import app.cli.app as cli_app_module
from typer.testing import CliRunner

from app.actions import ActionResult
from app.inbox import (
    AvitoChatRead,
    AvitoClientRead,
    AvitoListingRead,
    AvitoMessageRead,
)
from app.inbox.sync import InboxSyncResult
from app.main import cli
from app.modules import (
    AccountMutationResult,
    AccountSummary,
    LocalBootstrapSummary,
    ModuleMutationResult,
    ModuleOperationsError,
    ModuleRunAccessError,
    ModuleSettingMutationResult,
    ModuleSettingSummary,
    ModuleSummary,
)


runner = CliRunner()


class FakeOperationsService:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []
        self.set_module_calls: list[dict[str, object]] = []

    def create_account(self, **kwargs):
        self.create_calls.append(kwargs)
        return AccountMutationResult(
            created=True,
            account=AccountSummary(
                id=101,
                name=kwargs["name"],
                client_id=kwargs["client_id"],
                avito_user_id=kwargs.get("avito_user_id"),
                is_active=kwargs.get("is_active", True),
                last_inbox_sync_at=None,
                last_inbox_sync_status=None,
                last_inbox_error=None,
                created_at="2026-03-25T00:00:00Z",
                updated_at="2026-03-25T00:00:00Z",
            ),
        )

    def list_accounts(self):
        return (
            AccountSummary(
                id=101,
                name="Demo Account",
                client_id="demo-client",
                avito_user_id="avito-user-101",
                is_active=True,
                last_inbox_sync_at=None,
                last_inbox_sync_status="success",
                last_inbox_error=None,
                created_at="2026-03-25T00:00:00Z",
                updated_at="2026-03-25T00:00:00Z",
            ),
        )

    def create_module(self, **kwargs):
        return ModuleMutationResult(
            created=True,
            module=ModuleSummary(id=1, name=kwargs["name"]),
        )

    def list_modules(self):
        return (
            ModuleSummary(id=1, name="system_core"),
            ModuleSummary(id=2, name="module2_inbox"),
        )

    def ensure_default_modules(self):
        return self.list_modules()

    def set_module_state(self, **kwargs):
        self.set_module_calls.append(kwargs)
        return ModuleSettingMutationResult(
            created=True,
            module_setting=ModuleSettingSummary(
                account_id=kwargs["account_id"],
                module_id=1,
                module_name=kwargs.get("module_name") or "system_core",
                is_enabled=kwargs["is_enabled"],
                created_at="2026-03-25T00:00:00Z",
                updated_at="2026-03-25T00:00:00Z",
            ),
        )

    def list_module_settings(self, **kwargs):
        return (
            ModuleSettingSummary(
                account_id=kwargs.get("account_id") or 101,
                module_id=1,
                module_name=kwargs.get("module_name") or "system_core",
                is_enabled=True,
                created_at="2026-03-25T00:00:00Z",
                updated_at="2026-03-25T00:00:00Z",
            ),
        )

    def bootstrap_local(self, **kwargs):
        return LocalBootstrapSummary(
            account=AccountMutationResult(
                created=False,
                account=AccountSummary(
                    id=101,
                    name=kwargs["name"],
                    client_id=kwargs["client_id"],
                    avito_user_id=kwargs.get("avito_user_id"),
                    is_active=True,
                    last_inbox_sync_at=None,
                    last_inbox_sync_status=None,
                    last_inbox_error=None,
                    created_at="2026-03-25T00:00:00Z",
                    updated_at="2026-03-25T00:00:00Z",
                ),
            ),
            module_setting=ModuleSettingMutationResult(
                created=False,
                module_setting=ModuleSettingSummary(
                    account_id=101,
                    module_id=1,
                    module_name=kwargs["module_name"],
                    is_enabled=True,
                    created_at="2026-03-25T00:00:00Z",
                    updated_at="2026-03-25T00:00:00Z",
                ),
            ),
        )


class FakeInboxService:
    def sync_account_inbox(self, account_id: int) -> InboxSyncResult:
        return InboxSyncResult(
            account_id=account_id,
            account_name="Demo Account",
            synced_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
            status="success",
            last_error=None,
            chats_synced=1,
            messages_synced=2,
            clients_synced=1,
            listings_synced=1,
        )

    def list_chats(self, **kwargs):
        return (
            AvitoChatRead(
                id=1,
                account_id=kwargs["account_id"],
                external_chat_id="chat-1",
                chat_type="u2i",
                client_id=1,
                listing_id=1,
                external_created_at="2026-04-02T10:00:00Z",
                external_updated_at="2026-04-02T11:00:00Z",
                last_message_at="2026-04-02T11:00:00Z",
                last_message_id="message-2",
                last_message_direction="out",
                last_message_type="text",
                message_count=2,
                created_at="2026-04-02T11:00:00Z",
                updated_at="2026-04-02T11:00:00Z",
            ),
        )

    def list_messages(self, **kwargs):
        return (
            AvitoMessageRead(
                id=1,
                account_id=kwargs["account_id"],
                chat_id=kwargs.get("chat_id") or 1,
                external_message_id="message-1",
                author_external_id="2002",
                direction="in",
                message_type="text",
                text="Hello",
                content_json={"text": "Hello"},
                quote_json=None,
                is_read=True,
                read_at="2026-04-02T10:01:00Z",
                external_created_at="2026-04-02T10:00:00Z",
                created_at="2026-04-02T10:00:01Z",
            ),
        )

    def list_clients(self, **kwargs):
        return (
            AvitoClientRead(
                id=1,
                account_id=kwargs["account_id"],
                external_user_id="2002",
                display_name="Buyer",
                profile_url="https://avito.ru/user/buyer/profile",
                avatar_url="https://example.test/avatar.png",
                created_at="2026-04-02T10:00:00Z",
                updated_at="2026-04-02T10:00:00Z",
            ),
        )

    def list_listings(self, **kwargs):
        return (
            AvitoListingRead(
                id=1,
                account_id=kwargs["account_id"],
                external_item_id="1768287444",
                title="Mazda 3 2008",
                url="https://avito.ru/item/1768287444",
                price_string="300 000 RUB",
                status_id="10",
                owner_external_user_id="1001",
                image_url="https://example.test/item-140x105.jpg",
                created_at="2026-04-02T10:00:00Z",
                updated_at="2026-04-02T10:00:00Z",
            ),
        )


def test_check_system_command() -> None:
    result = runner.invoke(cli, ["check-system"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["version"] == "0.1.0"
    assert payload["account_identifier"] == "account_id"


def test_check_db_command(monkeypatch) -> None:
    monkeypatch.setattr(cli_app_module, "check_database_connection", lambda: None)

    result = runner.invoke(cli, ["check-db"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["database_url"].startswith("postgresql+psycopg://")


def test_run_probe_action_command(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_app_module,
        "execute_probe_action",
        lambda **kwargs: ActionResult(
            action_log_id=1,
            action_name="probe_dispatch",
            account_id=kwargs.get("account_id"),
            run_id=kwargs.get("run_id"),
            status="success",
            error_message=None,
            output={"target": kwargs["target"]},
        ),
    )

    result = runner.invoke(cli, ["run-probe-action", "target-1", "hello"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "success"
    assert payload["action_name"] == "probe_dispatch"


def test_create_account_command(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(cli_app_module, "get_module_operations_service", lambda: service)

    result = runner.invoke(
        cli,
        ["create-account", "Demo Account", "demo-client", "demo-secret"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["item"]["account"]["client_id"] == "demo-client"


def test_create_account_command_accepts_avito_user_id(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(cli_app_module, "get_module_operations_service", lambda: service)

    result = runner.invoke(
        cli,
        [
            "create-account",
            "Demo Account",
            "demo-client",
            "demo-secret",
            "--avito-user-id",
            "avito-user-101",
        ],
    )

    assert result.exit_code == 0
    assert service.create_calls[0]["avito_user_id"] == "avito-user-101"
    payload = json.loads(result.stdout)
    assert payload["item"]["account"]["avito_user_id"] == "avito-user-101"


def test_set_module_command(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(cli_app_module, "get_module_operations_service", lambda: service)

    result = runner.invoke(cli, ["set-module", "101", "system_core", "--enabled"])

    assert result.exit_code == 0
    assert service.set_module_calls[0]["account_id"] == 101
    payload = json.loads(result.stdout)
    assert payload["item"]["module_setting"]["is_enabled"] is True


def test_list_accounts_command(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(cli_app_module, "get_module_operations_service", lambda: service)

    result = runner.invoke(cli, ["list-accounts"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["id"] == 101
    assert payload["items"][0]["avito_user_id"] == "avito-user-101"
    assert payload["items"][0]["last_inbox_sync_status"] == "success"


def test_list_modules_command(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(cli_app_module, "get_module_operations_service", lambda: service)

    result = runner.invoke(cli, ["list-modules"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["name"] == "system_core"


def test_bootstrap_local_command(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(cli_app_module, "get_module_operations_service", lambda: service)

    result = runner.invoke(
        cli,
        [
            "bootstrap-local",
            "--name",
            "Local Dev Account",
            "--client-id",
            "local-dev-client",
            "--client-secret",
            "local-dev-secret",
            "--avito-user-id",
            "local-avito-user",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["item"]["account"]["account"]["client_id"] == "local-dev-client"
    assert payload["item"]["account"]["account"]["avito_user_id"] == "local-avito-user"


def test_run_job_command_passes_account_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeJobResult:
        status = "success"

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            return {"status": "success", "job_name": "account-system-probe", "account_id": 101}

    monkeypatch.setattr(
        cli_app_module,
        "run_registered_job",
        lambda **kwargs: captured.update(kwargs) or FakeJobResult(),
    )

    result = runner.invoke(cli, ["run-job", "account-system-probe", "--account-id", "101"])

    assert result.exit_code == 0
    assert captured["account_id"] == 101


def test_sync_inbox_command(monkeypatch) -> None:
    monkeypatch.setattr(cli_app_module, "get_inbox_service", lambda: FakeInboxService())

    result = runner.invoke(cli, ["sync-inbox", "--account-id", "101"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["item"]["account_id"] == 101
    assert payload["item"]["messages_synced"] == 2


def test_list_chats_command(monkeypatch) -> None:
    monkeypatch.setattr(cli_app_module, "get_inbox_service", lambda: FakeInboxService())

    result = runner.invoke(cli, ["list-chats", "--account-id", "101"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["external_chat_id"] == "chat-1"


def test_list_messages_command(monkeypatch) -> None:
    monkeypatch.setattr(cli_app_module, "get_inbox_service", lambda: FakeInboxService())

    result = runner.invoke(
        cli,
        ["list-messages", "--account-id", "101", "--chat-id", "1"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["external_message_id"] == "message-1"


def test_list_clients_command(monkeypatch) -> None:
    monkeypatch.setattr(cli_app_module, "get_inbox_service", lambda: FakeInboxService())

    result = runner.invoke(cli, ["list-clients", "--account-id", "101"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["external_user_id"] == "2002"


def test_list_listings_command(monkeypatch) -> None:
    monkeypatch.setattr(cli_app_module, "get_inbox_service", lambda: FakeInboxService())

    result = runner.invoke(cli, ["list-listings", "--account-id", "101"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["external_item_id"] == "1768287444"


def test_smoke_check_command(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_app_module,
        "run_smoke_check",
        lambda: {
            "status": "ok",
            "job_status": "success",
            "action_status": "success",
        },
    )

    result = runner.invoke(cli, ["smoke-check"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["action_status"] == "success"


def test_run_job_cli_renders_module_access_error(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_app_module,
        "run_registered_job",
        lambda **kwargs: (_ for _ in ()).throw(
            ModuleRunAccessError(
                "module_disabled",
                "Module 'system_core' is disabled for account '101'.",
            )
        ),
    )

    result = runner.invoke(cli, ["run-job", "account-system-probe", "--account-id", "101"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error_code"] == "module_disabled"


def test_create_account_cli_renders_operations_error(monkeypatch) -> None:
    class BrokenService(FakeOperationsService):
        def create_account(self, **kwargs):
            raise ModuleOperationsError("client_id_exists", "already exists")

    monkeypatch.setattr(
        cli_app_module,
        "get_module_operations_service",
        lambda: BrokenService(),
    )

    result = runner.invoke(
        cli,
        ["create-account", "Demo Account", "demo-client", "demo-secret"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "client_id_exists"
