"""Operational helpers for platform account and module management."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.db.models import AvitoAccount, Module, ModuleAccountSetting
from app.db.session import get_session_factory

DEFAULT_MODULE_NAMES = (
    "system_core",
    "module2_inbox",
)


class ModuleOperationsError(ValueError):
    """Raised when account/module operations fail."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AccountSummary(BaseModel):
    """Public account view without secret leakage."""

    id: int
    name: str
    client_id: str
    avito_user_id: str | None = None
    is_active: bool
    last_inbox_sync_at: datetime | None = None
    last_inbox_sync_status: str | None = None
    last_inbox_error: str | None = None
    created_at: datetime
    updated_at: datetime


class AccountMutationResult(BaseModel):
    """Account mutation result."""

    created: bool
    account: AccountSummary


class ModuleSummary(BaseModel):
    """Module catalog item."""

    id: int
    name: str


class ModuleMutationResult(BaseModel):
    """Module mutation result."""

    created: bool
    module: ModuleSummary


class ModuleSettingSummary(BaseModel):
    """Per-account module switch summary."""

    account_id: int
    module_id: int
    module_name: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class ModuleSettingMutationResult(BaseModel):
    """Module switch mutation result."""

    created: bool
    module_setting: ModuleSettingSummary


class LocalBootstrapSummary(BaseModel):
    """Bootstrap summary for local smoke flow."""

    account: AccountMutationResult
    module_setting: ModuleSettingMutationResult


class ModuleOperationsService:
    """Mutations and lookups for accounts and module catalog."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()

    def create_account(
        self,
        *,
        name: str,
        client_id: str,
        client_secret: str,
        avito_user_id: str | None = None,
        is_active: bool = True,
    ) -> AccountMutationResult:
        """Create one account."""
        normalized_name = self._normalize_non_empty(name, field="name")
        normalized_client_id = self._normalize_non_empty(client_id, field="client_id")
        normalized_secret = self._normalize_non_empty(client_secret, field="client_secret")
        normalized_avito_user_id = self._normalize_optional_non_empty(
            avito_user_id,
            field="avito_user_id",
        )

        with self._session_factory() as session:
            existing = session.execute(
                select(AvitoAccount).where(AvitoAccount.client_id == normalized_client_id)
            ).scalar_one_or_none()
            if existing is not None:
                raise ModuleOperationsError(
                    "client_id_exists",
                    f"Account with client_id '{normalized_client_id}' already exists.",
                )
            if normalized_avito_user_id is not None:
                existing_avito_user = session.execute(
                    select(AvitoAccount).where(
                        AvitoAccount.avito_user_id == normalized_avito_user_id
                    )
                ).scalar_one_or_none()
                if existing_avito_user is not None:
                    raise ModuleOperationsError(
                        "avito_user_id_exists",
                        (
                            "Account with avito_user_id "
                            f"'{normalized_avito_user_id}' already exists."
                        ),
                    )

            account = AvitoAccount(
                name=normalized_name,
                client_id=normalized_client_id,
                client_secret=normalized_secret,
                avito_user_id=normalized_avito_user_id,
                is_active=is_active,
            )
            session.add(account)
            session.commit()
            session.refresh(account)
            return AccountMutationResult(created=True, account=self._build_account_summary(account))

    def list_accounts(self) -> tuple[AccountSummary, ...]:
        """List accounts ordered by id."""
        with self._session_factory() as session:
            accounts = session.execute(select(AvitoAccount).order_by(AvitoAccount.id)).scalars()
            return tuple(self._build_account_summary(account) for account in accounts)

    def create_module(self, *, name: str) -> ModuleMutationResult:
        """Create one module catalog item."""
        normalized_name = self._normalize_non_empty(name, field="module_name")
        with self._session_factory() as session:
            existing = session.execute(
                select(Module).where(Module.name == normalized_name)
            ).scalar_one_or_none()
            if existing is not None:
                return ModuleMutationResult(created=False, module=self._build_module_summary(existing))

            module = Module(name=normalized_name)
            session.add(module)
            session.commit()
            session.refresh(module)
            return ModuleMutationResult(created=True, module=self._build_module_summary(module))

    def list_modules(self) -> tuple[ModuleSummary, ...]:
        """List module catalog."""
        with self._session_factory() as session:
            modules = session.execute(select(Module).order_by(Module.id)).scalars()
            return tuple(self._build_module_summary(item) for item in modules)

    def ensure_default_modules(
        self,
        module_names: Iterable[str] = DEFAULT_MODULE_NAMES,
    ) -> tuple[ModuleSummary, ...]:
        """Ensure standard module catalog rows exist."""
        summaries: list[ModuleSummary] = []
        for name in module_names:
            result = self.create_module(name=name)
            summaries.append(result.module)
        return tuple(summaries)

    def resolve_account_id(self, *, account_id: int | None) -> int | None:
        """Validate account id existence and return it."""
        if account_id is None:
            return None
        with self._session_factory() as session:
            account = session.get(AvitoAccount, account_id)
            if account is None:
                raise ModuleOperationsError(
                    "account_not_found",
                    f"Account '{account_id}' does not exist.",
                )
        return account_id

    def resolve_module_id(self, *, module_name: str) -> int:
        """Resolve module name to id."""
        normalized_name = self._normalize_non_empty(module_name, field="module_name")
        with self._session_factory() as session:
            module = session.execute(
                select(Module).where(Module.name == normalized_name)
            ).scalar_one_or_none()
            if module is None:
                raise ModuleOperationsError(
                    "module_not_found",
                    f"Module '{normalized_name}' does not exist.",
                )
            return module.id

    def set_module_state(
        self,
        *,
        account_id: int,
        is_enabled: bool,
        module_id: int | None = None,
        module_name: str | None = None,
    ) -> ModuleSettingMutationResult:
        """Create or update module switch for one account."""
        if module_id is None and module_name is None:
            raise ModuleOperationsError(
                "module_selector_missing",
                "Either module_id or module_name must be provided.",
            )

        with self._session_factory() as session:
            account = session.get(AvitoAccount, account_id)
            if account is None:
                raise ModuleOperationsError(
                    "account_not_found",
                    f"Account '{account_id}' does not exist.",
                )

            resolved_module_id = module_id
            if resolved_module_id is None:
                resolved_module = session.execute(
                    select(Module).where(Module.name == module_name)
                ).scalar_one_or_none()
                if resolved_module is None:
                    raise ModuleOperationsError(
                        "module_not_found",
                        f"Module '{module_name}' does not exist.",
                    )
                resolved_module_id = resolved_module.id

            module = session.get(Module, resolved_module_id)
            if module is None:
                raise ModuleOperationsError(
                    "module_not_found",
                    f"Module '{resolved_module_id}' does not exist.",
                )

            module_setting = session.get(
                ModuleAccountSetting,
                {"account_id": account.id, "module_id": module.id},
            )
            created = module_setting is None
            if module_setting is None:
                module_setting = ModuleAccountSetting(
                    account_id=account.id,
                    module_id=module.id,
                )

            module_setting.is_enabled = is_enabled
            session.add(module_setting)
            session.commit()
            session.refresh(module_setting)

            return ModuleSettingMutationResult(
                created=created,
                module_setting=self._build_module_setting_summary(
                    module_setting=module_setting,
                    module=module,
                ),
            )

    def list_module_settings(
        self,
        *,
        account_id: int | None = None,
        module_id: int | None = None,
        module_name: str | None = None,
    ) -> tuple[ModuleSettingSummary, ...]:
        """List module switches with optional filters."""
        with self._session_factory() as session:
            query = (
                select(ModuleAccountSetting)
                .options(joinedload(ModuleAccountSetting.module))
                .order_by(ModuleAccountSetting.account_id, ModuleAccountSetting.module_id)
            )
            if account_id is not None:
                query = query.where(ModuleAccountSetting.account_id == account_id)

            resolved_module_id = module_id
            if resolved_module_id is None and module_name is not None:
                module = session.execute(select(Module).where(Module.name == module_name)).scalar_one_or_none()
                if module is None:
                    return ()
                resolved_module_id = module.id

            if resolved_module_id is not None:
                query = query.where(ModuleAccountSetting.module_id == resolved_module_id)

            rows = session.execute(query).scalars()
            summaries: list[ModuleSettingSummary] = []
            for row in rows:
                if row.module is None:
                    continue
                summaries.append(
                    self._build_module_setting_summary(
                        module_setting=row,
                        module=row.module,
                    )
                )
            return tuple(summaries)

    def bootstrap_local(
        self,
        *,
        name: str = "Local Dev Account",
        client_id: str = "local-dev-client",
        client_secret: str = "local-dev-secret",
        avito_user_id: str | None = None,
        module_name: str = "system_core",
    ) -> LocalBootstrapSummary:
        """Idempotently bootstrap one local account and enable one core module."""
        normalized_name = self._normalize_non_empty(name, field="name")
        normalized_client_id = self._normalize_non_empty(client_id, field="client_id")
        normalized_secret = self._normalize_non_empty(client_secret, field="client_secret")
        normalized_avito_user_id = self._normalize_optional_non_empty(
            avito_user_id,
            field="avito_user_id",
        )
        normalized_module_name = self._normalize_non_empty(module_name, field="module_name")

        with self._session_factory() as session:
            account = session.execute(
                select(AvitoAccount).where(AvitoAccount.client_id == normalized_client_id)
            ).scalar_one_or_none()
            if normalized_avito_user_id is not None:
                account_by_avito_user = session.execute(
                    select(AvitoAccount).where(
                        AvitoAccount.avito_user_id == normalized_avito_user_id
                    )
                ).scalar_one_or_none()
                if account_by_avito_user is not None and (
                    account is None or account_by_avito_user.id != account.id
                ):
                    raise ModuleOperationsError(
                        "avito_user_id_exists",
                        (
                            "Account with avito_user_id "
                            f"'{normalized_avito_user_id}' already exists."
                        ),
                    )
            created_account = account is None
            if account is None:
                account = AvitoAccount(
                    name=normalized_name,
                    client_id=normalized_client_id,
                    client_secret=normalized_secret,
                    avito_user_id=normalized_avito_user_id,
                    is_active=True,
                )
            else:
                account.name = normalized_name
                account.client_secret = normalized_secret
                if normalized_avito_user_id is not None:
                    account.avito_user_id = normalized_avito_user_id
                account.is_active = True

            session.add(account)
            session.flush()

            module = session.execute(
                select(Module).where(Module.name == normalized_module_name)
            ).scalar_one_or_none()
            if module is None:
                module = Module(name=normalized_module_name)
                session.add(module)
                session.flush()

            module_setting = session.get(
                ModuleAccountSetting,
                {"account_id": account.id, "module_id": module.id},
            )
            created_setting = module_setting is None
            if module_setting is None:
                module_setting = ModuleAccountSetting(
                    account_id=account.id,
                    module_id=module.id,
                    is_enabled=True,
                )
            else:
                module_setting.is_enabled = True

            session.add(module_setting)
            session.commit()
            session.refresh(account)
            session.refresh(module_setting)
            session.refresh(module)

            return LocalBootstrapSummary(
                account=AccountMutationResult(
                    created=created_account,
                    account=self._build_account_summary(account),
                ),
                module_setting=ModuleSettingMutationResult(
                    created=created_setting,
                    module_setting=self._build_module_setting_summary(
                        module_setting=module_setting,
                        module=module,
                    ),
                ),
            )

    @staticmethod
    def _normalize_non_empty(value: str, *, field: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ModuleOperationsError(
                f"{field}_invalid",
                f"{field} must not be empty.",
            )
        return normalized

    @classmethod
    def _normalize_optional_non_empty(
        cls,
        value: str | None,
        *,
        field: str,
    ) -> str | None:
        if value is None:
            return None
        return cls._normalize_non_empty(value, field=field)

    @staticmethod
    def _build_account_summary(account: AvitoAccount) -> AccountSummary:
        return AccountSummary(
            id=account.id,
            name=account.name,
            client_id=account.client_id,
            avito_user_id=account.avito_user_id,
            is_active=account.is_active,
            last_inbox_sync_at=account.last_inbox_sync_at,
            last_inbox_sync_status=account.last_inbox_sync_status,
            last_inbox_error=account.last_inbox_error,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )

    @staticmethod
    def _build_module_summary(module: Module) -> ModuleSummary:
        return ModuleSummary(id=module.id, name=module.name)

    @staticmethod
    def _build_module_setting_summary(
        *,
        module_setting: ModuleAccountSetting,
        module: Module,
    ) -> ModuleSettingSummary:
        return ModuleSettingSummary(
            account_id=module_setting.account_id,
            module_id=module_setting.module_id,
            module_name=module.name,
            is_enabled=module_setting.is_enabled,
            created_at=module_setting.created_at,
            updated_at=module_setting.updated_at,
        )
