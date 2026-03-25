from __future__ import annotations

import pytest
from sqlalchemy import select
from uuid import uuid4

from app.db import AvitoAccount, Module, ModuleAccountSetting, get_session_factory
from app.modules import ModuleAccessService, ModuleRunAccessError


pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("require_postgresql"),
]


def _create_account_with_module_setting(
    *,
    is_active: bool,
    is_enabled: bool,
) -> int:
    session_factory = get_session_factory()
    suffix = uuid4().hex[:8]
    with session_factory() as session:
        module = session.execute(select(Module).where(Module.name == "module0")).scalar_one_or_none()
        if module is None:
            module = Module(name="module0")
            session.add(module)
            session.flush()

        account = AvitoAccount(
            name="Test Account",
            client_id=f"acc-client-{suffix}",
            client_secret=f"acc-secret-{suffix}",
            is_active=is_active,
        )
        session.add(account)
        session.flush()

        module_setting = ModuleAccountSetting(
            account_id=account.id,
            module_id=module.id,
            is_enabled=is_enabled,
        )
        session.add(module_setting)
        session.commit()
        return account.id


def test_module_access_allows_enabled_account() -> None:
    service = ModuleAccessService()
    account_id = _create_account_with_module_setting(is_active=True, is_enabled=True)

    decision = service.assert_job_can_run(
        module_name="module0",
        job_name="account-ping",
        account_id=account_id,
        requires_account=True,
    )

    assert decision.account is not None
    assert decision.account.id == account_id
    assert decision.module_setting is not None
    assert decision.module_setting.is_enabled is True


def test_module_access_rejects_missing_account() -> None:
    service = ModuleAccessService()

    with pytest.raises(ModuleRunAccessError, match="does not exist"):
        service.assert_job_can_run(
            module_name="module0",
            job_name="account-ping",
            account_id=999999999,
            requires_account=True,
        )


def test_module_access_rejects_disabled_module() -> None:
    service = ModuleAccessService()
    account_id = _create_account_with_module_setting(is_active=True, is_enabled=False)

    with pytest.raises(
        ModuleRunAccessError,
        match=f"Module 'module0' is disabled for account '{account_id}'",
    ):
        service.assert_job_can_run(
            module_name="module0",
            job_name="account-ping",
            account_id=account_id,
            requires_account=True,
        )
