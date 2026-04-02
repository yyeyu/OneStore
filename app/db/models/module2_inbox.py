"""SQLAlchemy models for the Module 2 inbox data slice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AvitoClient(Base):
    """Known Avito counterparty for one seller account."""

    __tablename__ = "avito_clients"
    __table_args__ = (
        UniqueConstraint("account_id", "external_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    account: Mapped["AvitoAccount"] = relationship(back_populates="avito_clients")
    chats: Mapped[list["AvitoChat"]] = relationship(back_populates="client")


class AvitoListingRef(Base):
    """Lightweight reference snapshot for a listing linked to chat traffic."""

    __tablename__ = "avito_listings_ref"
    __table_args__ = (
        UniqueConstraint("account_id", "external_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_string: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_external_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    account: Mapped["AvitoAccount"] = relationship(back_populates="avito_listings")
    chats: Mapped[list["AvitoChat"]] = relationship(back_populates="listing")


class AvitoChat(Base):
    """Inbox chat snapshot for one seller account."""

    __tablename__ = "avito_chats"
    __table_args__ = (
        UniqueConstraint("account_id", "external_chat_id"),
        Index("ix_avito_chats_account_id_last_message_at", "account_id", "last_message_at"),
        Index("ix_avito_chats_account_id_external_updated_at", "account_id", "external_updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_chat_id: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_type: Mapped[str] = mapped_column(String(32), nullable=False)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("avito_clients.id", ondelete="SET NULL"),
        nullable=True,
    )
    listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("avito_listings_ref.id", ondelete="SET NULL"),
        nullable=True,
    )
    external_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    external_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Keep the Avito message identifier directly in the chat summary to avoid
    # coupling list refreshes to an already-persisted internal message row.
    last_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_message_direction: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_message_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
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

    account: Mapped["AvitoAccount"] = relationship(back_populates="avito_chats")
    client: Mapped["AvitoClient | None"] = relationship(back_populates="chats")
    listing: Mapped["AvitoListingRef | None"] = relationship(back_populates="chats")
    messages: Mapped[list["AvitoMessage"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
    )


class AvitoMessage(Base):
    """Raw-normalized inbox message snapshot for one chat."""

    __tablename__ = "avito_messages"
    __table_args__ = (
        UniqueConstraint("account_id", "external_message_id"),
        Index("ix_avito_messages_chat_id_external_created_at", "chat_id", "external_created_at"),
        Index(
            "ix_avito_messages_account_id_external_created_at",
            "account_id",
            "external_created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("avito_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("avito_chats.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    quote_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    account: Mapped["AvitoAccount"] = relationship(back_populates="avito_messages")
    chat: Mapped["AvitoChat"] = relationship(back_populates="messages")
