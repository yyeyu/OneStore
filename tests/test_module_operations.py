from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.db import ModuleRun, get_session_factory
from app.jobs import run_registered_job
from app.modules import ModuleOperationsService


pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("require_postgresql"),
]


def test_module_operations_create_list_set_and_resolve_account_code() -> None:
    service = ModuleOperationsService()
    account_code = f"ops-{uuid4().hex[:10]}"

    create_result = service.create_account(
        account_code=account_code,
        display_name="Operations Test Account",
    )
    module_result = service.set_module_state(
        account_code=account_code,
        module_name="module0",
        is_enabled=True,
        settings_json={"note": "ready"},
    )
    accounts = service.list_accounts()
    module_settings = service.list_module_settings(account_code=account_code)
    resolved_account_id = service.resolve_account_id(account_code=account_code)

    assert create_result.created is True
    assert create_result.account.account_code == account_code
    assert any(account.account_code == account_code for account in accounts)
    assert module_result.module_setting.account_code == account_code
    assert module_result.module_setting.settings_json == {"note": "ready"}
    assert len(module_settings) == 1
    assert module_settings[0].module_name == "module0"
    assert resolved_account_id == create_result.account.account_id


def test_bootstrap_local_enables_module_and_runs_account_job() -> None:
    service = ModuleOperationsService()
    account_code = f"bootstrap-{uuid4().hex[:10]}"

    bootstrap = service.bootstrap_local(
        account_code=account_code,
        display_name="Bootstrap Test Account",
        module_name="module0",
    )
    job_result = run_registered_job(
        job_name="account-ping",
        trigger_source="manual",
        mode="dry_run",
        account_id=bootstrap.account.account.account_id,
    )

    session_factory = get_session_factory()
    with session_factory() as session:
        run_record = session.get(ModuleRun, UUID(job_result.run_id))

    assert bootstrap.account.account.account_code == account_code
    assert bootstrap.module_setting.module_setting.is_enabled is True
    assert job_result.status == "success"
    assert run_record is not None
    assert run_record.account_id == bootstrap.account.account.account_id
