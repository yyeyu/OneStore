from __future__ import annotations

from app.db import ModuleRun, get_session_factory
from app.jobs import run_registered_job
from app.modules import ModuleOperationsError, ModuleOperationsService
import pytest
from uuid import uuid4


pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("require_postgresql"),
]


def test_module_operations_create_and_list_entities() -> None:
    service = ModuleOperationsService()
    service.ensure_default_modules(["system_core", "module2_inbox"])
    suffix = uuid4().hex[:8]

    account_result = service.create_account(
        name="Operations Test Account",
        client_id=f"ops-client-{suffix}",
        client_secret=f"ops-secret-{suffix}",
        avito_user_id=f"avito-user-{suffix}",
    )
    module_result = service.set_module_state(
        account_id=account_result.account.id,
        module_name="system_core",
        is_enabled=True,
    )

    accounts = service.list_accounts()
    modules = service.list_modules()
    module_settings = service.list_module_settings(account_id=account_result.account.id)
    resolved_module_id = service.resolve_module_id(module_name="system_core")

    assert any(account.id == account_result.account.id for account in accounts)
    assert any(module.name == "system_core" for module in modules)
    assert any(module.name == "module2_inbox" for module in modules)
    assert module_result.module_setting.module_name == "system_core"
    assert module_result.module_setting.is_enabled is True
    assert len(module_settings) == 1
    assert module_settings[0].module_id == resolved_module_id
    assert account_result.account.avito_user_id == f"avito-user-{suffix}"
    assert account_result.account.last_inbox_sync_at is None
    assert account_result.account.last_inbox_sync_status is None
    assert account_result.account.last_inbox_error is None


def test_bootstrap_local_enables_module_and_runs_account_job() -> None:
    service = ModuleOperationsService()
    suffix = uuid4().hex[:8]
    bootstrap = service.bootstrap_local(
        name="Bootstrap Test Account",
        client_id=f"bootstrap-client-{suffix}",
        client_secret=f"bootstrap-secret-{suffix}",
        avito_user_id=f"bootstrap-avito-{suffix}",
        module_name="system_core",
    )

    job_result = run_registered_job(
        job_name="account-system-probe",
        trigger_source="manual",
        account_id=bootstrap.account.account.id,
    )

    session_factory = get_session_factory()
    with session_factory() as session:
        run_record = session.get(ModuleRun, job_result.run_id)

    assert bootstrap.module_setting.module_setting.is_enabled is True
    assert bootstrap.account.account.avito_user_id == f"bootstrap-avito-{suffix}"
    assert job_result.status == "success"
    assert run_record is not None
    assert run_record.account_id == bootstrap.account.account.id


def test_create_account_rejects_duplicate_avito_user_id() -> None:
    service = ModuleOperationsService()
    suffix = uuid4().hex[:8]
    avito_user_id = f"duplicate-avito-{suffix}"

    service.create_account(
        name="First Inbox Account",
        client_id=f"first-client-{suffix}",
        client_secret=f"first-secret-{suffix}",
        avito_user_id=avito_user_id,
    )

    with pytest.raises(ModuleOperationsError, match="already exists"):
        service.create_account(
            name="Second Inbox Account",
            client_id=f"second-client-{suffix}",
            client_secret=f"second-secret-{suffix}",
            avito_user_id=avito_user_id,
        )
