"""Operational account/module bootstrap helpers for Module 0."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.db.models import AvitoAccount, ModuleAccountSetting
from app.db.session import get_session_factory


class ModuleOperationsError(ValueError):
    """Raised when operational account/module commands cannot be completed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AccountSummary(BaseModel):
    """Human-facing account summary keyed by account_code."""

    account_id: UUID
    account_code: str
    display_name: str
    external_account_id: str | None
    is_active: bool


class AccountMutationResult(BaseModel):
    """Result of create/bootstrap account mutation."""

    created: bool
    account: AccountSummary


class ModuleSettingSummary(BaseModel):
    """Human-facing module setting summary joined with account_code."""

    setting_id: UUID
    account_id: UUID
    account_code: str
    module_name: str
    is_enabled: bool
    settings_json: dict[str, Any] | None


class ModuleSettingMutationResult(BaseModel):
    """Result of enable/disable/bootstrap module mutation."""

    created: bool
    module_setting: ModuleSettingSummary


class LocalBootstrapSummary(BaseModel):
    """Idempotent bootstrap result for local development."""

    account_identifier: str = "account_code"
    account: AccountMutationResult
    module_setting: ModuleSettingMutationResult


class ModuleOperationsService:
    """Operational service for accounts and module settings.

    `account_code` is the primary human-facing identifier for operators and
    local development workflows. Internal UUIDs remain the canonical DB ids.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()

    def create_account(
        self,
        *,
        account_code: str,
        display_name: str,
        external_account_id: str | None = None,
        is_active: bool = True,
    ) -> AccountMutationResult:
        """Create a new Avito account using account_code as the operator key."""
        normalized_code = self._normalize_account_code(account_code)
        normalized_display_name = self._normalize_display_name(display_name)

        with self._session_factory() as session:
            self._ensure_account_code_available(
                session,
                account_code=normalized_code,
            )
            self._ensure_external_account_id_available(
                session,
                external_account_id=external_account_id,
            )

            account = AvitoAccount(
                account_code=normalized_code,
                display_name=normalized_display_name,
                external_account_id=external_account_id,
                is_active=is_active,
            )
            session.add(account)
            session.commit()
            session.refresh(account)

            return AccountMutationResult(
                created=True,
                account=self._build_account_summary(account),
            )

    def list_accounts(self) -> tuple[AccountSummary, ...]:
        """Return all accounts ordered by account_code for operator workflows."""
        with self._session_factory() as session:
            accounts = session.execute(
                select(AvitoAccount).order_by(AvitoAccount.account_code)
            ).scalars()
            return tuple(self._build_account_summary(account) for account in accounts)

    def resolve_account_id(
        self,
        *,
        account_id: UUID | None = None,
        account_code: str | None = None,
    ) -> UUID | None:
        """Resolve the preferred operator-facing account selector into internal UUID."""
        if account_id is None and account_code is None:
            return None

        with self._session_factory() as session:
            account: AvitoAccount | None = None

            if account_code is not None:
                normalized_code = self._normalize_account_code(account_code)
                account = self._get_account_by_code(
                    session,
                    account_code=normalized_code,
                )
                if account is None:
                    raise ModuleOperationsError(
                        "account_not_found",
                        f"Account '{normalized_code}' does not exist.",
                    )

            if account_id is not None and account is not None and account.id != account_id:
                raise ModuleOperationsError(
                    "account_identity_mismatch",
                    (
                        f"Account id '{account_id}' does not match "
                        f"account_code '{account_code}'."
                    ),
                )

            return account.id if account is not None else account_id

    def set_module_state(
        self,
        *,
        account_code: str,
        module_name: str,
        is_enabled: bool,
        settings_json: dict[str, Any] | None = None,
    ) -> ModuleSettingMutationResult:
        """Create or update per-account module settings using account_code."""
        normalized_code = self._normalize_account_code(account_code)

        with self._session_factory() as session:
            account = self._get_account_by_code(session, account_code=normalized_code)
            if account is None:
                raise ModuleOperationsError(
                    "account_not_found",
                    f"Account '{normalized_code}' does not exist.",
                )

            module_setting = session.execute(
                select(ModuleAccountSetting).where(
                    ModuleAccountSetting.account_id == account.id,
                    ModuleAccountSetting.module_name == module_name,
                )
            ).scalar_one_or_none()

            created = module_setting is None
            if module_setting is None:
                module_setting = ModuleAccountSetting(
                    account_id=account.id,
                    module_name=module_name,
                )

            module_setting.is_enabled = is_enabled
            if settings_json is not None:
                module_setting.settings_json = settings_json
            elif module_setting.settings_json is None:
                module_setting.settings_json = {}

            session.add(module_setting)
            session.commit()
            session.refresh(module_setting)

            return ModuleSettingMutationResult(
                created=created,
                module_setting=self._build_module_setting_summary(
                    account=account,
                    module_setting=module_setting,
                ),
            )

    def list_module_settings(
        self,
        *,
        account_code: str | None = None,
        module_name: str | None = None,
    ) -> tuple[ModuleSettingSummary, ...]:
        """Return joined module settings, optionally filtered by account_code/module."""
        with self._session_factory() as session:
            query = (
                select(ModuleAccountSetting)
                .options(joinedload(ModuleAccountSetting.account))
                .join(ModuleAccountSetting.account)
                .order_by(AvitoAccount.account_code, ModuleAccountSetting.module_name)
            )
            if account_code is not None:
                query = query.where(
                    AvitoAccount.account_code == self._normalize_account_code(account_code)
                )
            if module_name is not None:
                query = query.where(ModuleAccountSetting.module_name == module_name)

            settings = session.execute(query).scalars()
            return tuple(
                self._build_module_setting_summary(
                    account=module_setting.account,
                    module_setting=module_setting,
                )
                for module_setting in settings
                if module_setting.account is not None
            )

    def bootstrap_local(
        self,
        *,
        account_code: str = "local-dev",
        display_name: str = "Local Dev Account",
        module_name: str = "module0",
        external_account_id: str | None = None,
    ) -> LocalBootstrapSummary:
        """Idempotently prepare one local dev account and enable the requested module."""
        account_result = self._ensure_account(
            account_code=account_code,
            display_name=display_name,
            external_account_id=external_account_id,
        )
        module_result = self.set_module_state(
            account_code=account_result.account.account_code,
            module_name=module_name,
            is_enabled=True,
            settings_json=None,
        )
        return LocalBootstrapSummary(
            account=account_result,
            module_setting=module_result,
        )

    def _ensure_account(
        self,
        *,
        account_code: str,
        display_name: str,
        external_account_id: str | None,
    ) -> AccountMutationResult:
        normalized_code = self._normalize_account_code(account_code)
        normalized_display_name = self._normalize_display_name(display_name)

        with self._session_factory() as session:
            account = self._get_account_by_code(session, account_code=normalized_code)
            if account is None:
                self._ensure_external_account_id_available(
                    session,
                    external_account_id=external_account_id,
                )
                account = AvitoAccount(
                    account_code=normalized_code,
                    display_name=normalized_display_name,
                    external_account_id=external_account_id,
                    is_active=True,
                )
                session.add(account)
                session.commit()
                session.refresh(account)
                return AccountMutationResult(
                    created=True,
                    account=self._build_account_summary(account),
                )

            if (
                external_account_id is not None
                and account.external_account_id != external_account_id
            ):
                self._ensure_external_account_id_available(
                    session,
                    external_account_id=external_account_id,
                    ignore_account_id=account.id,
                )
                account.external_account_id = external_account_id

            account.display_name = normalized_display_name
            account.is_active = True
            session.add(account)
            session.commit()
            session.refresh(account)
            return AccountMutationResult(
                created=False,
                account=self._build_account_summary(account),
            )

    @staticmethod
    def _normalize_account_code(account_code: str) -> str:
        normalized = account_code.strip()
        if not normalized:
            raise ModuleOperationsError(
                "account_code_invalid",
                "account_code must not be empty.",
            )
        return normalized

    @staticmethod
    def _normalize_display_name(display_name: str) -> str:
        normalized = display_name.strip()
        if not normalized:
            raise ModuleOperationsError(
                "display_name_invalid",
                "display_name must not be empty.",
            )
        return normalized

    @staticmethod
    def _get_account_by_code(
        session: Session,
        *,
        account_code: str,
    ) -> AvitoAccount | None:
        return session.execute(
            select(AvitoAccount).where(AvitoAccount.account_code == account_code)
        ).scalar_one_or_none()

    @staticmethod
    def _ensure_account_code_available(
        session: Session,
        *,
        account_code: str,
    ) -> None:
        existing = ModuleOperationsService._get_account_by_code(
            session,
            account_code=account_code,
        )
        if existing is not None:
            raise ModuleOperationsError(
                "account_code_exists",
                f"Account '{account_code}' already exists.",
            )

    @staticmethod
    def _ensure_external_account_id_available(
        session: Session,
        *,
        external_account_id: str | None,
        ignore_account_id: UUID | None = None,
    ) -> None:
        if external_account_id is None:
            return

        query = select(AvitoAccount).where(
            AvitoAccount.external_account_id == external_account_id
        )
        if ignore_account_id is not None:
            query = query.where(AvitoAccount.id != ignore_account_id)

        existing = session.execute(query).scalar_one_or_none()
        if existing is not None:
            raise ModuleOperationsError(
                "external_account_id_exists",
                (
                    f"external_account_id '{external_account_id}' is already used by "
                    f"account '{existing.account_code}'."
                ),
            )

    @staticmethod
    def _build_account_summary(account: AvitoAccount) -> AccountSummary:
        return AccountSummary(
            account_id=account.id,
            account_code=account.account_code,
            display_name=account.display_name,
            external_account_id=account.external_account_id,
            is_active=account.is_active,
        )

    @staticmethod
    def _build_module_setting_summary(
        *,
        account: AvitoAccount,
        module_setting: ModuleAccountSetting,
    ) -> ModuleSettingSummary:
        return ModuleSettingSummary(
            setting_id=module_setting.id,
            account_id=account.id,
            account_code=account.account_code,
            module_name=module_setting.module_name,
            is_enabled=module_setting.is_enabled,
            settings_json=module_setting.settings_json,
        )
