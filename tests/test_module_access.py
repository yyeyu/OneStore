from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.db import AvitoAccount, ModuleAccountSetting, get_session_factory
from app.modules import ModuleAccessService, ModuleRunAccessError


pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("require_postgresql"),
]


def _create_account_with_module_setting(
    *,
    is_active: bool,
    is_enabled: bool,
) -> tuple[UUID, str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        account = AvitoAccount(
            account_code=f"acc-{uuid4().hex[:12]}",
            display_name="Test Account",
            is_active=is_active,
        )
        session.add(account)
        session.flush()

        module_setting = ModuleAccountSetting(
            account_id=account.id,
            module_name="module0",
            is_enabled=is_enabled,
            settings_json={"note": "ok"},
        )
        session.add(module_setting)
        session.commit()

        return account.id, account.account_code


def test_module_access_allows_enabled_account() -> None:
    service = ModuleAccessService()
    account_id, _ = _create_account_with_module_setting(
        is_active=True,
        is_enabled=True,
    )

    decision = service.assert_job_can_run(
        module_name="module0",
        job_name="account-ping",
        account_id=account_id,
        requires_account=True,
    )

    assert decision is not None
    assert decision.account.id == account_id
    assert decision.module_setting.is_enabled is True


def test_module_access_rejects_missing_account() -> None:
    service = ModuleAccessService()

    with pytest.raises(ModuleRunAccessError, match="does not exist"):
        service.assert_job_can_run(
            module_name="module0",
            job_name="account-ping",
            account_id=uuid4(),
            requires_account=True,
        )


def test_module_access_rejects_disabled_module() -> None:
    service = ModuleAccessService()
    account_id, account_code = _create_account_with_module_setting(
        is_active=True,
        is_enabled=False,
    )

    with pytest.raises(
        ModuleRunAccessError,
        match=f"Module 'module0' is disabled for account '{account_code}'",
    ):
        service.assert_job_can_run(
            module_name="module0",
            job_name="account-ping",
            account_id=account_id,
            requires_account=True,
        )
