"""Account/module access checks for job execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.db.models import AvitoAccount, Module, ModuleAccountSetting
from app.db.session import get_session_factory


class ModuleRunAccessError(ValueError):
    """Raised when a job cannot run for the requested account/module."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModuleRunAccessDecision:
    """Validated execution context for one job run."""

    module: Module
    account: AvitoAccount | None
    module_setting: ModuleAccountSetting | None


class ModuleAccessService:
    """Central access guard for jobs."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()

    def assert_job_can_run(
        self,
        *,
        module_name: str,
        job_name: str,
        account_id: int | None,
        requires_account: bool,
    ) -> ModuleRunAccessDecision:
        """Validate account/module state and return the resolved module."""
        with self._session_factory() as session:
            module = session.execute(
                select(Module).where(Module.name == module_name)
            ).scalar_one_or_none()
            if module is None:
                raise ModuleRunAccessError(
                    "module_not_found",
                    f"Module '{module_name}' does not exist.",
                )

            if account_id is None and not requires_account:
                return ModuleRunAccessDecision(module=module, account=None, module_setting=None)

            if account_id is None:
                raise ModuleRunAccessError(
                    "account_required",
                    f"Job '{job_name}' requires account_id.",
                )

            account = session.get(AvitoAccount, account_id)
            if account is None:
                raise ModuleRunAccessError(
                    "account_not_found",
                    f"Account '{account_id}' does not exist.",
                )
            if not account.is_active:
                raise ModuleRunAccessError(
                    "account_inactive",
                    f"Account '{account_id}' is inactive.",
                )

            module_setting = session.get(
                ModuleAccountSetting,
                {"account_id": account_id, "module_id": module.id},
            )
            if module_setting is None:
                raise ModuleRunAccessError(
                    "module_settings_missing",
                    (
                        f"Module '{module_name}' has no settings for "
                        f"account '{account_id}'."
                    ),
                )
            if not module_setting.is_enabled:
                raise ModuleRunAccessError(
                    "module_disabled",
                    (
                        f"Module '{module_name}' is disabled for "
                        f"account '{account_id}'."
                    ),
                )

            return ModuleRunAccessDecision(
                module=module,
                account=account,
                module_setting=module_setting,
            )

    def list_runnable_account_ids(
        self,
        *,
        module_name: str,
        job_name: str,
    ) -> tuple[int, ...]:
        """Return active accounts with enabled module flag."""
        _ = job_name  # Kept for stable call signature.
        with self._session_factory() as session:
            module = session.execute(
                select(Module).where(Module.name == module_name)
            ).scalar_one_or_none()
            if module is None:
                raise ModuleRunAccessError(
                    "module_not_found",
                    f"Module '{module_name}' does not exist.",
                )

            rows = session.execute(
                select(ModuleAccountSetting)
                .options(joinedload(ModuleAccountSetting.account))
                .where(
                    ModuleAccountSetting.module_id == module.id,
                    ModuleAccountSetting.is_enabled.is_(True),
                )
            ).scalars()

            result: list[int] = []
            for row in rows:
                account = row.account
                if account is None or not account.is_active:
                    continue
                result.append(account.id)
            return tuple(result)
