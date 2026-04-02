"""Platform core models aligned with the simplified database schema."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AvitoAccount(Base):
    """Connected Avito account with API credentials and inbox sync state."""

    __tablename__ = "avito_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    client_secret: Mapped[str] = mapped_column(Text, nullable=False)
    avito_user_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    last_inbox_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_inbox_sync_status: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    last_inbox_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    module_settings: Mapped[list["ModuleAccountSetting"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    module_runs: Mapped[list["ModuleRun"]] = relationship(back_populates="account")
    action_logs: Mapped[list["ActionLog"]] = relationship(back_populates="account")
    avito_clients: Mapped[list["AvitoClient"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    avito_listings: Mapped[list["AvitoListingRef"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    avito_chats: Mapped[list["AvitoChat"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    avito_messages: Mapped[list["AvitoMessage"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )


class Module(Base):
    """Module catalog entry."""

    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    module_settings: Mapped[list["ModuleAccountSetting"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
    )
    module_runs: Mapped[list["ModuleRun"]] = relationship(back_populates="module")


class ModuleAccountSetting(Base):
    """Per-account module switch."""

    __tablename__ = "module_account_settings"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    module_id: Mapped[int] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    account: Mapped["AvitoAccount"] = relationship(back_populates="module_settings")
    module: Mapped["Module"] = relationship(back_populates="module_settings")


class ModuleRun(Base):
    """Job execution journal."""

    __tablename__ = "module_runs"
    __table_args__ = (
        Index("ix_module_runs_account_id", "account_id"),
        Index("ix_module_runs_module_id", "module_id"),
        Index("ix_module_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    module_id: Mapped[int] = mapped_column(
        ForeignKey("modules.id"),
        nullable=False,
    )
    job_name: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    account: Mapped["AvitoAccount | None"] = relationship(back_populates="module_runs")
    module: Mapped["Module"] = relationship(back_populates="module_runs")
    action_logs: Mapped[list["ActionLog"]] = relationship(back_populates="run")


class ActionLog(Base):
    """Audit log for outward actions."""

    __tablename__ = "action_logs"
    __table_args__ = (
        Index("ix_action_logs_account_id", "account_id"),
        Index("ix_action_logs_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("module_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    account: Mapped["AvitoAccount | None"] = relationship(back_populates="action_logs")
    run: Mapped["ModuleRun | None"] = relationship(back_populates="action_logs")
