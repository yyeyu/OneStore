"""Typer CLI for local platform operations."""

from __future__ import annotations

import json
import logging
from typing import Any

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
    """Return account/module operations service."""
    return ModuleOperationsService()


def _configure_runtime_logging() -> None:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        settings.log_format,
        service=settings.app_name,
        environment=settings.environment,
    )


def _emit_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, indent=2))


def _emit_cli_error(*, code: str, message: str) -> None:
    _emit_json(
        {
            "status": "error",
            "error_code": code,
            "error": message,
        }
    )
    raise typer.Exit(code=1)


def _emit_job_result(result) -> None:
    _emit_json(result.model_dump(mode="json"))
    if result.status == "error":
        raise typer.Exit(code=1)


def _emit_action_result(result) -> None:
    _emit_json(result.model_dump(mode="json"))
    if result.status == "error":
        raise typer.Exit(code=1)


@cli.command("check-system")
def check_system() -> None:
    """Print current platform configuration summary."""
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
    """Validate current database connection settings."""
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
        _emit_json(
            {
                "status": "error",
                "database_url": masked_database_url,
                "error": str(exc),
            }
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
    _emit_json(
        {
            "status": "ok",
            "database_url": masked_database_url,
        }
    )


@cli.command("create-account")
def create_account(
    name: str = typer.Argument(..., help="Human-readable account name."),
    client_id: str = typer.Argument(..., help="API client id."),
    client_secret: str = typer.Argument(..., help="API client secret."),
    is_active: bool = typer.Option(
        True,
        "--active/--inactive",
        help="Initial active flag.",
    ),
) -> None:
    """Create one account."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()

    try:
        result = operations_service.create_account(
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            is_active=is_active,
        )
    except ModuleOperationsError as exc:
        _emit_cli_error(code=exc.code, message=str(exc))

    _emit_json({"status": "ok", "item": result.model_dump(mode="json")})


@cli.command("list-accounts")
def list_accounts() -> None:
    """List accounts without exposing client_secret."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()
    accounts = operations_service.list_accounts()
    _emit_json(
        {
            "status": "ok",
            "items": [account.model_dump(mode="json") for account in accounts],
        }
    )


@cli.command("create-module")
def create_module(
    module_name: str = typer.Argument(..., help="Module catalog name."),
) -> None:
    """Create one module catalog entry."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()
    result = operations_service.create_module(name=module_name)
    _emit_json({"status": "ok", "item": result.model_dump(mode="json")})


@cli.command("list-modules")
def list_modules() -> None:
    """List module catalog."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()
    modules = operations_service.list_modules()
    _emit_json({"status": "ok", "items": [item.model_dump(mode="json") for item in modules]})


@cli.command("ensure-default-modules")
def ensure_default_modules() -> None:
    """Seed default module catalog entries."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()
    modules = operations_service.ensure_default_modules()
    _emit_json({"status": "ok", "items": [item.model_dump(mode="json") for item in modules]})


@cli.command("set-module")
def set_module(
    account_id: int = typer.Argument(..., help="Target account id."),
    module_name: str = typer.Argument(..., help="Module name from catalog."),
    is_enabled: bool = typer.Option(
        True,
        "--enabled/--disabled",
        help="Enable or disable module for account.",
    ),
) -> None:
    """Enable or disable one module for one account."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()

    try:
        result = operations_service.set_module_state(
            account_id=account_id,
            module_name=module_name,
            is_enabled=is_enabled,
        )
    except ModuleOperationsError as exc:
        _emit_cli_error(code=exc.code, message=str(exc))

    _emit_json({"status": "ok", "item": result.model_dump(mode="json")})


@cli.command("list-module-settings")
def list_module_settings(
    account_id: int | None = typer.Option(None, help="Optional account id filter."),
    module_name: str | None = typer.Option(None, help="Optional module name filter."),
) -> None:
    """List module settings."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()
    items = operations_service.list_module_settings(
        account_id=account_id,
        module_name=module_name,
    )
    _emit_json({"status": "ok", "items": [item.model_dump(mode="json") for item in items]})


@cli.command("bootstrap-local")
def bootstrap_local(
    name: str = typer.Option("Local Dev Account", help="Display name for local account."),
    client_id: str = typer.Option("local-dev-client", help="Client id for local account."),
    client_secret: str = typer.Option(
        "local-dev-secret",
        help="Client secret for local account.",
    ),
    module_name: str = typer.Option("module0", help="Module to enable."),
) -> None:
    """Idempotently bootstrap one local account and enable one module."""
    _configure_runtime_logging()
    operations_service = get_module_operations_service()
    try:
        result = operations_service.bootstrap_local(
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            module_name=module_name,
        )
    except ModuleOperationsError as exc:
        _emit_cli_error(code=exc.code, message=str(exc))
    _emit_json({"status": "ok", "item": result.model_dump(mode="json")})


@cli.command("run-job")
def run_job(
    job_name: str = typer.Argument(..., help="Registered job name."),
    account_id: int | None = typer.Option(None, help="Optional account id."),
    trigger_source: str = typer.Option(
        "manual",
        "--trigger-source",
        help="Run source: manual/scheduler/event/retry.",
    ),
    fail: bool = typer.Option(
        False,
        "--fail",
        help="Force ping job to fail for lifecycle checks.",
    ),
) -> None:
    """Run one registered job."""
    _configure_runtime_logging()
    if trigger_source not in {"manual", "scheduler", "event", "retry"}:
        _emit_cli_error(
            code="trigger_source_invalid",
            message="trigger_source must be one of: manual, scheduler, event, retry.",
        )

    try:
        result = run_registered_job(
            job_name=job_name,
            trigger_source=trigger_source,
            account_id=account_id,
            should_fail=fail,
        )
    except (ModuleRunAccessError, ModuleOperationsError) as exc:
        _emit_cli_error(code=exc.code, message=str(exc))

    _emit_job_result(result)


@cli.command("run-test-job")
def run_test_job(
    account_id: int | None = typer.Option(None, help="Optional account id."),
    fail: bool = typer.Option(False, "--fail", help="Force ping job to fail."),
) -> None:
    """Alias for run-job ping."""
    run_job(
        job_name="ping",
        account_id=account_id,
        trigger_source="manual",
        fail=fail,
    )


@cli.command("run-scheduler")
def run_scheduler(
    interval_seconds: int | None = typer.Option(
        None,
        "--interval-seconds",
        help="Override interval for local checks.",
    ),
    duration_seconds: int | None = typer.Option(
        None,
        "--duration-seconds",
        help="Run scheduler for N seconds then stop.",
    ),
) -> None:
    """Start APScheduler loop for registered jobs."""
    _configure_runtime_logging()
    summary = run_scheduler_loop(
        interval_seconds=interval_seconds,
        duration_seconds=duration_seconds,
    )
    _emit_json(summary)


@cli.command("run-demo-action")
def run_demo_action(
    target: str = typer.Argument(..., help="Demo target identifier."),
    message: str = typer.Argument(..., help="Demo message payload."),
    account_id: int | None = typer.Option(None, help="Optional account id."),
    run_id: int | None = typer.Option(None, help="Optional module run id."),
    fail: bool = typer.Option(
        False,
        "--fail",
        help="Force demo action to fail.",
    ),
) -> None:
    """Run demo action through simplified ActionExecutor."""
    _configure_runtime_logging()
    result = execute_demo_action(
        target=target,
        message=message,
        account_id=account_id,
        run_id=run_id,
        should_fail=fail,
    )
    _emit_action_result(result)


@cli.command("smoke-check")
def smoke_check() -> None:
    """Run a compact local smoke-check."""
    _configure_runtime_logging()
    summary = run_smoke_check()
    _emit_json(summary)


@cli.command("serve")
def serve(
    host: str | None = typer.Option(None, help="Host override."),
    port: int | None = typer.Option(None, help="Port override."),
    reload: bool = typer.Option(False, help="Enable auto-reload."),
) -> None:
    """Run FastAPI server."""
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
