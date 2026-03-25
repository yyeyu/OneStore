"""Typer CLI for local platform operations."""

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
import typer
import uvicorn

from app.actions import execute_demo_action
from app.core.diagnostics import build_system_summary
from app.core.logging import configure_logging
from app.core.smoke import run_smoke_check
from app.core.settings import get_settings
from app.db.session import check_database_connection
from app.jobs import run_registered_job, run_scheduler_loop
from app.modules import ModuleOperationsError, ModuleOperationsService, ModuleRunAccessError

cli = typer.Typer(
    add_completion=False,
    help="Avito AI Assistant platform CLI.",
    no_args_is_help=True,
)


def get_module_operations_service() -> ModuleOperationsService:
    """Return the operational service for account/module bootstrap workflows."""
    return ModuleOperationsService()


def _configure_runtime_logging() -> None:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        settings.log_format,
        service=settings.app_name,
        environment=settings.environment,
    )


@cli.command("check-system")
def check_system() -> None:
    """Print the current platform configuration summary."""
    settings = get_settings()
    _configure_runtime_logging()
    logging.getLogger(__name__).info(
        "System check completed",
        extra={
            "module_name": "system",
            "status": "ok",
        },
    )
    _emit_json(build_system_summary(settings))


@cli.command("check-db")
def check_db() -> None:
    """Validate the current database connection settings."""
    settings = get_settings()
    _configure_runtime_logging()
    masked_database_url = make_url(settings.database_url).render_as_string(
        hide_password=True
    )

    try:
        check_database_connection()
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).exception(
            "Database check failed",
            extra={
                "module_name": "system",
                "status": "error",
                "database_url": masked_database_url,
            },
        )
        typer.echo(
            json.dumps(
                {
                    "status": "error",
                    "database_url": masked_database_url,
                    "error": str(exc),
                },
                indent=2,
            )
        )
        raise typer.Exit(code=1) from exc

    logging.getLogger(__name__).info(
        "Database check completed",
        extra={
            "module_name": "system",
            "status": "ok",
            "database_url": masked_database_url,
        },
    )
    typer.echo(
        json.dumps(
            {
                "status": "ok",
                "database_url": masked_database_url,
            },
            indent=2,
        )
    )


def _emit_job_result(result) -> None:
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    if result.status in {"error", "locked"}:
        raise typer.Exit(code=1)


def _emit_action_result(result) -> None:
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    if result.status == "error":
        raise typer.Exit(code=1)


def _emit_cli_error(*, code: str, message: str) -> None:
    typer.echo(
        json.dumps(
            {
                "status": "error",
                "error_code": code,
                "error": message,
            },
            indent=2,
        )
    )
    raise typer.Exit(code=1)


def _emit_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, indent=2))


def _parse_settings_json(settings_json: str | None) -> dict[str, Any] | None:
    if settings_json is None:
        return None

    try:
        parsed = json.loads(settings_json)
    except json.JSONDecodeError as exc:
        _emit_cli_error(
            code="settings_json_invalid",
            message=f"settings_json must be valid JSON: {exc.msg}.",
        )

    if not isinstance(parsed, dict):
        _emit_cli_error(
            code="settings_json_invalid",
            message="settings_json must be a JSON object.",
        )

    return parsed


def _resolve_account_id(
    *,
    account_id: UUID | None,
    account_code: str | None,
    operations_service: ModuleOperationsService,
) -> UUID | None:
    try:
        return operations_service.resolve_account_id(
            account_id=account_id,
            account_code=account_code,
        )
    except ModuleOperationsError as exc:
        _emit_cli_error(code=exc.code, message=str(exc))
        return None


@cli.command("create-account")
def create_account(
    account_code: str = typer.Argument(..., help="Primary human-facing account identifier."),
    display_name: str = typer.Argument(..., help="Human-readable account name."),
    external_account_id: str | None = typer.Option(
        None,
        help="Optional external integration account id.",
    ),
    is_active: bool = typer.Option(
        True,
        "--active/--inactive",
        help="Initial active flag for the account.",
    ),
) -> None:
    """Create a new account using account_code as the operator-facing key."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()

    try:
        result = operations_service.create_account(
            account_code=account_code,
            display_name=display_name,
            external_account_id=external_account_id,
            is_active=is_active,
        )
    except ModuleOperationsError as exc:
        _emit_cli_error(code=exc.code, message=str(exc))

    _emit_json(
        {
            "status": "ok",
            "account_identifier": "account_code",
            "item": result.model_dump(mode="json"),
        }
    )


@cli.command("list-accounts")
def list_accounts() -> None:
    """List accounts using account_code as the main working identifier."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()
    accounts = operations_service.list_accounts()

    _emit_json(
        {
            "status": "ok",
            "account_identifier": "account_code",
            "items": [account.model_dump(mode="json") for account in accounts],
        }
    )


@cli.command("set-module")
def set_module(
    account_code: str = typer.Argument(..., help="Operator-facing account_code."),
    module_name: str = typer.Argument(..., help="Module name to configure."),
    is_enabled: bool = typer.Option(
        True,
        "--enabled/--disabled",
        help="Enable or disable the module for this account.",
    ),
    settings_json: str | None = typer.Option(
        None,
        "--settings-json",
        help="Optional JSON object for module settings.",
    ),
) -> None:
    """Enable or disable one module for one account without manual SQL."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()

    try:
        result = operations_service.set_module_state(
            account_code=account_code,
            module_name=module_name,
            is_enabled=is_enabled,
            settings_json=_parse_settings_json(settings_json),
        )
    except ModuleOperationsError as exc:
        _emit_cli_error(code=exc.code, message=str(exc))

    _emit_json(
        {
            "status": "ok",
            "account_identifier": "account_code",
            "item": result.model_dump(mode="json"),
        }
    )


@cli.command("list-module-settings")
def list_module_settings(
    account_code: str | None = typer.Option(
        None,
        help="Optional account_code filter.",
    ),
    module_name: str | None = typer.Option(
        None,
        help="Optional module filter.",
    ),
) -> None:
    """List module settings joined with account_code for operators."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()
    items = operations_service.list_module_settings(
        account_code=account_code,
        module_name=module_name,
    )

    _emit_json(
        {
            "status": "ok",
            "account_identifier": "account_code",
            "items": [item.model_dump(mode="json") for item in items],
        }
    )


@cli.command("bootstrap-local")
def bootstrap_local(
    account_code: str = typer.Option(
        "local-dev",
        "--account-code",
        help="Primary account_code for local development.",
    ),
    display_name: str = typer.Option(
        "Local Dev Account",
        "--display-name",
        help="Display name for the local development account.",
    ),
    module_name: str = typer.Option(
        "module0",
        "--module-name",
        help="Module name to enable for local bootstrap.",
    ),
    external_account_id: str | None = typer.Option(
        None,
        help="Optional external integration account id.",
    ),
) -> None:
    """Idempotently create one local dev account and enable one module."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()

    try:
        result = operations_service.bootstrap_local(
            account_code=account_code,
            display_name=display_name,
            module_name=module_name,
            external_account_id=external_account_id,
        )
    except ModuleOperationsError as exc:
        _emit_cli_error(code=exc.code, message=str(exc))

    _emit_json(
        {
            "status": "ok",
            "account_identifier": "account_code",
            "item": result.model_dump(mode="json"),
        }
    )


@cli.command("run-job")
def run_job(
    job_name: str = typer.Argument(..., help="Registered demo job name."),
    account_id: UUID | None = typer.Option(None, help="Optional account UUID."),
    account_code: str | None = typer.Option(
        None,
        help="Preferred human-facing account_code selector.",
    ),
    correlation_id: str | None = typer.Option(
        None,
        help="Optional correlation id override.",
    ),
    trigger_source: str = typer.Option(
        "manual",
        "--trigger-source",
        help="Run source label. Use manual or retry for CLI executions.",
    ),
    live: bool = typer.Option(False, "--live", help="Run the demo job in live mode."),
    fail: bool = typer.Option(
        False,
        "--fail",
        help="Force the demo ping job to fail for lifecycle testing.",
    ),
) -> None:
    """Run a registered demo job through the shared JobRunner."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()
    resolved_account_id = _resolve_account_id(
        account_id=account_id,
        account_code=account_code,
        operations_service=operations_service,
    )

    try:
        result = run_registered_job(
            job_name=job_name,
            trigger_source=trigger_source,
            mode="live" if live else "dry_run",
            account_id=resolved_account_id,
            correlation_id=correlation_id,
            should_fail=fail,
        )
    except (ModuleRunAccessError, ModuleOperationsError) as exc:
        _emit_cli_error(code=exc.code, message=str(exc))

    _emit_job_result(result)


@cli.command("run-test-job")
def run_test_job(
    account_id: UUID | None = typer.Option(None, help="Optional account UUID."),
    account_code: str | None = typer.Option(
        None,
        help="Preferred human-facing account_code selector.",
    ),
    correlation_id: str | None = typer.Option(
        None,
        help="Optional correlation id override.",
    ),
    live: bool = typer.Option(False, "--live", help="Run the demo job in live mode."),
    fail: bool = typer.Option(
        False,
        "--fail",
        help="Force the demo ping job to fail for lifecycle testing.",
    ),
) -> None:
    """Backward-compatible alias for running the ping demo job manually."""
    run_job(
        job_name="ping",
        account_id=account_id,
        account_code=account_code,
        correlation_id=correlation_id,
        trigger_source="manual",
        live=live,
        fail=fail,
    )


@cli.command("run-scheduler")
def run_scheduler(
    live: bool = typer.Option(False, "--live", help="Run scheduled jobs in live mode."),
    interval_seconds: int | None = typer.Option(
        None,
        "--interval-seconds",
        help="Override demo job interval for local checks.",
    ),
    duration_seconds: int | None = typer.Option(
        None,
        "--duration-seconds",
        help="Run scheduler for N seconds then stop.",
    ),
) -> None:
    """Start the APScheduler bootstrap for registered demo jobs."""
    _configure_runtime_logging()

    summary = run_scheduler_loop(
        mode="live" if live else "dry_run",
        interval_seconds=interval_seconds,
        duration_seconds=duration_seconds,
    )
    typer.echo(json.dumps(summary, indent=2))


@cli.command("run-demo-action")
def run_demo_action(
    target: str = typer.Argument(..., help="Demo target identifier."),
    message: str = typer.Argument(..., help="Demo message payload."),
    account_id: UUID | None = typer.Option(None, help="Optional account UUID."),
    run_id: UUID | None = typer.Option(None, help="Optional module run UUID."),
    correlation_id: str | None = typer.Option(
        None,
        help="Optional correlation id override.",
    ),
    live: bool = typer.Option(False, "--live", help="Use the live action branch."),
    fail: bool = typer.Option(
        False,
        "--fail",
        help="Force the demo action to fail for audit checks.",
    ),
) -> None:
    """Run the demonstration action through the shared Action layer."""
    _configure_runtime_logging()

    result = execute_demo_action(
        target=target,
        message=message,
        mode="live" if live else "dry_run",
        account_id=account_id,
        run_id=run_id,
        correlation_id=correlation_id,
        should_fail=fail,
    )
    _emit_action_result(result)


@cli.command("smoke-check")
def smoke_check() -> None:
    """Run a compact local smoke-check for Module 0 readiness."""
    _configure_runtime_logging()

    summary = run_smoke_check()
    typer.echo(json.dumps(summary, indent=2))


@cli.command("serve")
def serve(
    host: str | None = typer.Option(None, help="Host override."),
    port: int | None = typer.Option(None, help="Port override."),
    reload: bool = typer.Option(False, help="Enable auto-reload."),
) -> None:
    """Run the FastAPI server."""
    settings = get_settings()
    _configure_runtime_logging()

    bind_host = host or settings.host
    bind_port = port or settings.port

    logging.getLogger(__name__).info(
        "Starting API server",
        extra={
            "module_name": "system",
            "status": "started",
            "host": bind_host,
            "port": bind_port,
            "reload": reload,
        },
    )

    uvicorn.run(
        "app.main:app",
        host=bind_host,
        port=bind_port,
        reload=reload,
        factory=False,
    )
