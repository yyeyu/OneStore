import app.cli.app as cli_app_module

from typer.testing import CliRunner

from app.core.settings import Settings
from app.db.base import Base
from app.db.models import ActionLog, AvitoAccount, Module, ModuleAccountSetting, ModuleRun
from app.db.session import make_engine
from app.main import cli


runner = CliRunner()


def test_metadata_registers_expected_tables() -> None:
    assert set(Base.metadata.tables) == {
        "action_logs",
        "avito_accounts",
        "module_account_settings",
        "module_runs",
        "modules",
    }


def test_models_expose_expected_table_names() -> None:
    assert AvitoAccount.__tablename__ == "avito_accounts"
    assert Module.__tablename__ == "modules"
    assert ModuleAccountSetting.__tablename__ == "module_account_settings"
    assert ModuleRun.__tablename__ == "module_runs"
    assert ActionLog.__tablename__ == "action_logs"


def test_make_engine_uses_postgresql_settings() -> None:
    engine = make_engine(
        Settings(
            database_url=(
                "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/"
                "avito_ai_assistant_test"
            )
        )
    )

    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.host == "127.0.0.1"
        assert engine.url.port == 5433
        assert engine.url.database == "avito_ai_assistant_test"
    finally:
        engine.dispose()


def test_check_db_command_reports_success_with_mocked_connection(monkeypatch) -> None:
    monkeypatch.setattr(cli_app_module, "check_database_connection", lambda: None)

    result = runner.invoke(cli, ["check-db"])

    assert result.exit_code == 0
    assert '"status": "ok"' in result.stdout


def test_domain_tables_are_not_present_in_metadata() -> None:
    forbidden_tables = {
        "products",
        "items",
        "ads",
        "chats",
        "messages",
        "cases",
        "statuses",
        "idempotency_keys",
    }
    assert forbidden_tables.isdisjoint(Base.metadata.tables.keys())
