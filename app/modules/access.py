"""Account and module-setting access checks for Module 0 jobs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.db.models import AvitoAccount, ModuleAccountSetting
from app.db.session import get_session_factory


class ModuleRunAccessError(ValueError):
    """Raised when a job cannot be started for the requested account/module."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ModuleSettingsPayload(BaseModel):
    """Minimal validated shape for Module 0 account settings."""

    model_config = ConfigDict(extra="allow")


@dataclass(frozen=True)
class ModuleRunAccessDecision:
    """Validated account/module context for a job run."""

    account: AvitoAccount
    module_setting: ModuleAccountSetting
    settings: ModuleSettingsPayload


class AvitoAccountRepository:
    """Read-only access to registered Avito accounts."""

    @staticmethod
    def get_by_id(session: Session, account_id: UUID) -> AvitoAccount | None:
        return session.get(AvitoAccount, account_id)


class ModuleAccountSettingRepository:
    """Read-only access to per-account module settings."""

    @staticmethod
    def get_by_account_and_module(
        session: Session,
        *,
        account_id: UUID,
        module_name: str,
    ) -> ModuleAccountSetting | None:
        return session.execute(
            select(ModuleAccountSetting)
            .options(joinedload(ModuleAccountSetting.account))
            .where(
                ModuleAccountSetting.account_id == account_id,
                ModuleAccountSetting.module_name == module_name,
            )
        ).scalar_one_or_none()

    @staticmethod
    def list_enabled_by_module(
        session: Session,
        *,
        module_name: str,
    ) -> tuple[ModuleAccountSetting, ...]:
        return tuple(
            session.execute(
                select(ModuleAccountSetting)
                .options(joinedload(ModuleAccountSetting.account))
                .where(
                    ModuleAccountSetting.module_name == module_name,
                    ModuleAccountSetting.is_enabled.is_(True),
                )
            ).scalars()
        )


class ModuleAccessService:
    """Centralized guard for account-scoped module execution."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
        account_repository: AvitoAccountRepository | None = None,
        module_settings_repository: ModuleAccountSettingRepository | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()
        self._accounts = account_repository or AvitoAccountRepository()
        self._module_settings = (
            module_settings_repository or ModuleAccountSettingRepository()
        )
        self._logger = logging.getLogger(__name__)

    def assert_job_can_run(
        self,
        *,
        module_name: str,
        job_name: str,
        account_id: UUID | None,
        requires_account: bool,
    ) -> ModuleRunAccessDecision | None:
        """Validate whether a job may run for the requested account/module."""
        if account_id is None and not requires_account:
            return None

        if account_id is None:
            raise ModuleRunAccessError(
                "account_required",
                f"Job '{job_name}' requires account_id.",
            )

        with self._session_factory() as session:
            account = self._accounts.get_by_id(session, account_id)
            if account is None:
                raise ModuleRunAccessError(
                    "account_not_found",
                    f"Account '{account_id}' does not exist.",
                )

            if not account.is_active:
                raise ModuleRunAccessError(
                    "account_inactive",
                    f"Account '{account.account_code}' is inactive.",
                )

            module_setting = self._module_settings.get_by_account_and_module(
                session,
                account_id=account_id,
                module_name=module_name,
            )
            if module_setting is None:
                raise ModuleRunAccessError(
                    "module_settings_missing",
                    (
                        f"Module '{module_name}' has no settings for "
                        f"account '{account.account_code}'."
                    ),
                )

            if not module_setting.is_enabled:
                raise ModuleRunAccessError(
                    "module_disabled",
                    (
                        f"Module '{module_name}' is disabled for "
                        f"account '{account.account_code}'."
                    ),
                )

            settings = self._validate_settings(
                module_name=module_name,
                account_code=account.account_code,
                settings_json=module_setting.settings_json,
            )

            return ModuleRunAccessDecision(
                account=account,
                module_setting=module_setting,
                settings=settings,
            )

    def list_runnable_account_ids(
        self,
        *,
        module_name: str,
        job_name: str,
    ) -> tuple[UUID, ...]:
        """Return active account ids with enabled, valid settings for a module."""
        runnable_account_ids: list[UUID] = []

        with self._session_factory() as session:
            module_settings = self._module_settings.list_enabled_by_module(
                session,
                module_name=module_name,
            )

            for module_setting in module_settings:
                account = module_setting.account
                if account is None:
                    continue
                if not account.is_active:
                    self._logger.warning(
                        "Skipping scheduler account because account is inactive",
                        extra={
                            "job_name": job_name,
                            "module_name": module_name,
                            "account_id": str(account.id),
                        },
                    )
                    continue

                try:
                    self._validate_settings(
                        module_name=module_name,
                        account_code=account.account_code,
                        settings_json=module_setting.settings_json,
                    )
                except ModuleRunAccessError as exc:
                    self._logger.warning(
                        "Skipping scheduler account because module settings are invalid",
                        extra={
                            "job_name": job_name,
                            "module_name": module_name,
                            "account_id": str(account.id),
                            "error": str(exc),
                        },
                    )
                    continue

                runnable_account_ids.append(account.id)

        return tuple(runnable_account_ids)

    @staticmethod
    def _validate_settings(
        *,
        module_name: str,
        account_code: str,
        settings_json: dict[str, Any] | None,
    ) -> ModuleSettingsPayload:
        if settings_json is None:
            return ModuleSettingsPayload()

        try:
            return ModuleSettingsPayload.model_validate(settings_json)
        except ValidationError as exc:
            raise ModuleRunAccessError(
                "module_settings_invalid",
                (
                    f"Module '{module_name}' has invalid settings for "
                    f"account '{account_code}': {exc.errors(include_url=False)}"
                ),
            ) from exc
