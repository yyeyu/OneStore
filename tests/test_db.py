from sqlalchemy import UniqueConstraint

import app.cli.app as cli_app_module

from typer.testing import CliRunner

from app.core.settings import Settings
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
from app.db.session import make_engine
from app.main import cli


runner = CliRunner()


def test_metadata_registers_expected_tables() -> None:
    assert set(Base.metadata.tables) == {
        "action_logs",
        "avito_accounts",
        "avito_chats",
        "avito_clients",
        "avito_listings_ref",
        "avito_messages",
        "module_account_settings",
        "module_runs",
        "modules",
    }


def test_models_expose_expected_table_names() -> None:
    assert AvitoAccount.__tablename__ == "avito_accounts"
    assert AvitoChat.__tablename__ == "avito_chats"
    assert AvitoClient.__tablename__ == "avito_clients"
    assert AvitoListingRef.__tablename__ == "avito_listings_ref"
    assert AvitoMessage.__tablename__ == "avito_messages"
    assert Module.__tablename__ == "modules"
    assert ModuleAccountSetting.__tablename__ == "module_account_settings"
    assert ModuleRun.__tablename__ == "module_runs"
    assert ActionLog.__tablename__ == "action_logs"


def test_avito_account_model_exposes_inbox_sync_columns() -> None:
    account_columns = Base.metadata.tables["avito_accounts"].columns.keys()

    assert "avito_user_id" in account_columns
    assert "last_inbox_sync_at" in account_columns
    assert "last_inbox_sync_status" in account_columns
    assert "last_inbox_error" in account_columns


def test_module2_inbox_tables_expose_expected_constraints_and_indexes() -> None:
    chats_table = Base.metadata.tables["avito_chats"]
    messages_table = Base.metadata.tables["avito_messages"]
    clients_table = Base.metadata.tables["avito_clients"]
    listings_table = Base.metadata.tables["avito_listings_ref"]

    chats_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in chats_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    messages_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in messages_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    clients_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in clients_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    listings_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in listings_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("account_id", "external_chat_id") in chats_uniques
    assert ("account_id", "external_message_id") in messages_uniques
    assert ("account_id", "external_user_id") in clients_uniques
    assert ("account_id", "external_item_id") in listings_uniques

    chats_indexes = {tuple(index.columns.keys()) for index in chats_table.indexes}
    messages_indexes = {tuple(index.columns.keys()) for index in messages_table.indexes}

    assert ("account_id", "last_message_at") in chats_indexes
    assert ("account_id", "external_updated_at") in chats_indexes
    assert ("chat_id", "external_created_at") in messages_indexes
    assert ("account_id", "external_created_at") in messages_indexes
    assert messages_table.c.content_json.nullable is False


def test_make_engine_uses_postgresql_settings() -> None:
    engine = make_engine(
        Settings(
            database_url=(
                "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/"
                "onestore_test"
            )
        )
    )

    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.host == "127.0.0.1"
        assert engine.url.port == 5433
        assert engine.url.database == "onestore_test"
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
