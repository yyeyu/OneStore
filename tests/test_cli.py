import json
from uuid import UUID, uuid4

import app.cli.app as cli_app_module
from typer.testing import CliRunner

from app.actions import ActionResult
from app.main import cli
from app.modules import (
    AccountMutationResult,
    AccountSummary,
    LocalBootstrapSummary,
    ModuleOperationsError,
    ModuleRunAccessError,
    ModuleSettingMutationResult,
    ModuleSettingSummary,
)


runner = CliRunner()


class FakeOperationsService:
    def __init__(self) -> None:
        self.account_id = uuid4()
        self.setting_id = uuid4()
        self.create_calls: list[dict[str, object]] = []
        self.set_module_calls: list[dict[str, object]] = []
        self.resolve_calls: list[dict[str, object]] = []

    def create_account(self, **kwargs):
        self.create_calls.append(kwargs)
        return AccountMutationResult(
            created=True,
            account=AccountSummary(
                account_id=self.account_id,
                account_code=kwargs["account_code"],
                display_name=kwargs["display_name"],
                external_account_id=kwargs.get("external_account_id"),
                is_active=kwargs.get("is_active", True),
            ),
        )

    def list_accounts(self):
        return (
            AccountSummary(
                account_id=self.account_id,
                account_code="acc-demo",
                display_name="Demo Account",
                external_account_id=None,
                is_active=True,
            ),
        )

    def set_module_state(self, **kwargs):
        self.set_module_calls.append(kwargs)
        return ModuleSettingMutationResult(
            created=True,
            module_setting=ModuleSettingSummary(
                setting_id=self.setting_id,
                account_id=self.account_id,
                account_code=kwargs["account_code"],
                module_name=kwargs["module_name"],
                is_enabled=kwargs["is_enabled"],
                settings_json=kwargs.get("settings_json") or {},
            ),
        )

    def list_module_settings(self, **kwargs):
        return (
            ModuleSettingSummary(
                setting_id=self.setting_id,
                account_id=self.account_id,
                account_code=kwargs.get("account_code") or "acc-demo",
                module_name=kwargs.get("module_name") or "module0",
                is_enabled=True,
                settings_json={"note": "ok"},
            ),
        )

    def bootstrap_local(self, **kwargs):
        return LocalBootstrapSummary(
            account=AccountMutationResult(
                created=False,
                account=AccountSummary(
                    account_id=self.account_id,
                    account_code=kwargs["account_code"],
                    display_name=kwargs["display_name"],
                    external_account_id=kwargs.get("external_account_id"),
                    is_active=True,
                ),
            ),
            module_setting=ModuleSettingMutationResult(
                created=False,
                module_setting=ModuleSettingSummary(
                    setting_id=self.setting_id,
                    account_id=self.account_id,
                    account_code=kwargs["account_code"],
                    module_name=kwargs["module_name"],
                    is_enabled=True,
                    settings_json={},
                ),
            ),
        )

    def resolve_account_id(
        self,
        *,
        account_id: UUID | None = None,
        account_code: str | None = None,
    ) -> UUID | None:
        self.resolve_calls.append(
            {
                "account_id": account_id,
                "account_code": account_code,
            }
        )
        if account_code == "missing":
            raise ModuleOperationsError(
                "account_not_found",
                "Account 'missing' does not exist.",
            )
        return self.account_id if account_code is not None else account_id


def test_check_system_command() -> None:
    result = runner.invoke(cli, ["check-system"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["version"] == "0.1.0"
    assert payload["log_format"] == "text"
    assert payload["account_identifier"] == "account_code"


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
            action_log_id="action-log-1",
            module_name="module0",
            action_name="demo_dispatch",
            account_id=None,
            run_id=None,
            correlation_id="corr-1",
            mode="dry_run",
            status="dry_run",
            idempotency_key="key-1",
            duplicate=False,
            request_payload={"target": kwargs["target"]},
            result_payload={"mock_effect_applied": False},
            error_message=None,
        ),
    )

    result = runner.invoke(cli, ["run-demo-action", "target-1", "hello"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry_run"
    assert payload["action_name"] == "demo_dispatch"


def test_create_account_command(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(
        cli_app_module,
        "get_module_operations_service",
        lambda: service,
    )

    result = runner.invoke(cli, ["create-account", "acc-demo", "Demo Account"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["account_identifier"] == "account_code"
    assert payload["item"]["account"]["account_code"] == "acc-demo"


def test_set_module_command_parses_settings_json(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(
        cli_app_module,
        "get_module_operations_service",
        lambda: service,
    )

    result = runner.invoke(
        cli,
        [
            "set-module",
            "acc-demo",
            "module0",
            "--settings-json",
            "{\"interval\": 15}",
        ],
    )

    assert result.exit_code == 0
    assert service.set_module_calls[0]["settings_json"] == {"interval": 15}
    payload = json.loads(result.stdout)
    assert payload["item"]["module_setting"]["is_enabled"] is True


def test_list_accounts_command(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(
        cli_app_module,
        "get_module_operations_service",
        lambda: service,
    )

    result = runner.invoke(cli, ["list-accounts"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["account_code"] == "acc-demo"


def test_bootstrap_local_command(monkeypatch) -> None:
    service = FakeOperationsService()
    monkeypatch.setattr(
        cli_app_module,
        "get_module_operations_service",
        lambda: service,
    )

    result = runner.invoke(cli, ["bootstrap-local", "--account-code", "local-dev"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["item"]["account"]["account"]["account_code"] == "local-dev"


def test_run_job_command_resolves_account_code(monkeypatch) -> None:
    service = FakeOperationsService()
    captured: dict[str, object] = {}

    class FakeJobResult:
        status = "success"

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            return {"status": "success", "job_name": "account-ping"}

    monkeypatch.setattr(
        cli_app_module,
        "get_module_operations_service",
        lambda: service,
    )
    monkeypatch.setattr(
        cli_app_module,
        "run_registered_job",
        lambda **kwargs: captured.update(kwargs) or FakeJobResult(),
    )

    result = runner.invoke(cli, ["run-job", "account-ping", "--account-code", "acc-demo"])

    assert result.exit_code == 0
    assert service.resolve_calls[0]["account_code"] == "acc-demo"
    assert captured["account_id"] == service.account_id


def test_smoke_check_command(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_app_module,
        "run_smoke_check",
        lambda: {
            "status": "ok",
            "job_status": "success",
            "action_dry_run_status": "dry_run",
            "action_live_status": "success",
        },
    )

    result = runner.invoke(cli, ["smoke-check"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["action_dry_run_status"] == "dry_run"
    assert payload["action_live_status"] == "success"


def test_run_job_cli_renders_module_access_error(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_app_module,
        "run_registered_job",
        lambda **kwargs: (_ for _ in ()).throw(
            ModuleRunAccessError(
                "module_disabled",
                "Module 'module0' is disabled for account 'acc-demo'.",
            )
        ),
    )

    result = runner.invoke(cli, ["run-job", "account-ping", "--account-id", str(uuid4())])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error_code"] == "module_disabled"
