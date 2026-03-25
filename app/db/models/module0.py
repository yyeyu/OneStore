"""Technical Module 0 models only."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import Uuid as SqlUuid
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AvitoAccount(Base):
    """Registry of Avito accounts known to the platform."""

    __tablename__ = "avito_accounts"

    id: Mapped[UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid4)
    account_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    module_settings: Mapped[list[ModuleAccountSetting]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    module_runs: Mapped[list[ModuleRun]] = relationship(back_populates="account")
    action_logs: Mapped[list[ActionLog]] = relationship(back_populates="account")
    idempotency_keys: Mapped[list[IdempotencyKey]] = relationship(
        back_populates="account"
    )


class ModuleAccountSetting(Base):
    """Per-account toggles and configuration for platform modules."""

    __tablename__ = "module_account_settings"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "module_name",
            name="uq_module_account_settings_account_id_module_name",
        ),
    )

    id: Mapped[UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    settings_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    account: Mapped[AvitoAccount] = relationship(back_populates="module_settings")


class ModuleRun(Base):
    """Unified run journal for future jobs and technical workflows."""

    __tablename__ = "module_runs"
    __table_args__ = (
        Index("ix_module_runs_module_name_job_name", "module_name", "job_name"),
        Index("ix_module_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid4)
    module_name: Mapped[str] = mapped_column(String(64), nullable=False)
    job_name: Mapped[str] = mapped_column(String(128), nullable=False)
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    account: Mapped[AvitoAccount | None] = relationship(back_populates="module_runs")
    action_logs: Mapped[list[ActionLog]] = relationship(back_populates="run")
    idempotency_keys: Mapped[list[IdempotencyKey]] = relationship(
        back_populates="run"
    )


class ActionLog(Base):
    """Audit trail for future Action layer executions."""

    __tablename__ = "action_logs"
    __table_args__ = (
        Index("ix_action_logs_module_name_action_name", "module_name", "action_name"),
    )

    id: Mapped[UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid4)
    module_name: Mapped[str] = mapped_column(String(64), nullable=False)
    action_name: Mapped[str] = mapped_column(String(128), nullable=False)
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("module_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(191), nullable=True, index=True
    )
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped[AvitoAccount | None] = relationship(back_populates="action_logs")
    run: Mapped[ModuleRun | None] = relationship(back_populates="action_logs")


class IdempotencyKey(Base):
    """Generic reservation table for idempotency and lightweight locks."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("scope", "key", name="uq_idempotency_keys_scope_key"),
        Index("ix_idempotency_keys_status_locked_until", "status", "locked_until"),
    )

    id: Mapped[UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(191), nullable=False)
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("module_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'active'")
    )
    payload_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped[AvitoAccount | None] = relationship(back_populates="idempotency_keys")
    run: Mapped[ModuleRun | None] = relationship(back_populates="idempotency_keys")
