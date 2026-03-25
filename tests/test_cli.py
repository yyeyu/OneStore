import json

import app.cli.app as cli_app_module
from typer.testing import CliRunner

from app.actions import ActionResult
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
                is_active=kwargs.get("is_active", True),
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
                is_active=True,
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
            ModuleSummary(id=1, name="module0"),
            ModuleSummary(id=2, name="messaging"),
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
                module_name=kwargs.get("module_name") or "module0",
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
                module_name=kwargs.get("module_name") or "module0",
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
                    is_active=True,
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


def test_run_demo_action_command(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_app_module,
        "execute_demo_action",
        lambda **kwargs: ActionResult(
            action_log_id=1,
            action_name="demo_dispatch",
            account_id=kwargs.get("account_id"),
            run_id=kwargs.get("run_id"),
            status="success",
            error_message=None,
            output={"target": kwargs["target"]},
        ),
    )

    result = runner.invoke(cli, ["run-demo-action", "target-1", "hello"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "success"
    assert payload["action_name"] == "demo_dispatch"


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


def test_set_module_command(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(cli_app_module, "get_module_operations_service", lambda: service)

    result = runner.invoke(cli, ["set-module", "101", "module0", "--enabled"])

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


def test_list_modules_command(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(cli_app_module, "get_module_operations_service", lambda: service)

    result = runner.invoke(cli, ["list-modules"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["name"] == "module0"


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
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["item"]["account"]["account"]["client_id"] == "local-dev-client"


def test_run_job_command_passes_account_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeJobResult:
        status = "success"

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            return {"status": "success", "job_name": "account-ping", "account_id": 101}

    monkeypatch.setattr(
        cli_app_module,
        "run_registered_job",
        lambda **kwargs: captured.update(kwargs) or FakeJobResult(),
    )

    result = runner.invoke(cli, ["run-job", "account-ping", "--account-id", "101"])

    assert result.exit_code == 0
    assert captured["account_id"] == 101


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
                "Module 'module0' is disabled for account '101'.",
            )
        ),
    )

    result = runner.invoke(cli, ["run-job", "account-ping", "--account-id", "101"])

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
