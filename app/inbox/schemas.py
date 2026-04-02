"""Pydantic schemas for the Module 2 inbox data slice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AvitoClientRead(BaseModel):
    """Read model for one Avito counterparty."""

    id: int
    account_id: int
    external_user_id: str
    display_name: str | None = None
    profile_url: str | None = None
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime


class AvitoListingRead(BaseModel):
    """Read model for one listing reference."""

    id: int
    account_id: int
    external_item_id: str
    title: str | None = None
    url: str | None = None
    price_string: str | None = None
    status_id: str | None = None
    owner_external_user_id: str | None = None
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime


class AvitoChatRead(BaseModel):
    """Read model for one inbox chat."""

    id: int
    account_id: int
    external_chat_id: str
    chat_type: str
    client_id: int | None = None
    listing_id: int | None = None
    external_created_at: datetime
    external_updated_at: datetime
    last_message_at: datetime | None = None
    last_message_id: str | None = None
    last_message_direction: str | None = None
    last_message_type: str | None = None
    message_count: int | None = None
    created_at: datetime
    updated_at: datetime


class AvitoMessageRead(BaseModel):
    """Read model for one normalized inbox message."""

    id: int
    account_id: int
    chat_id: int
    external_message_id: str
    author_external_id: str | None = None
    direction: str
    message_type: str
    text: str | None = None
    content_json: dict[str, Any]
    quote_json: dict[str, Any] | None = None
    is_read: bool | None = None
    read_at: datetime | None = None
    external_created_at: datetime
    created_at: datetime


class ChatDetailsRead(BaseModel):
    """Read model for full chat details view."""

    chat: AvitoChatRead
    client: AvitoClientRead | None = None
    listing: AvitoListingRead | None = None
    messages: tuple[AvitoMessageRead, ...] = Field(default_factory=tuple)


class SyncAccountSummary(BaseModel):
    """Compact per-account sync state for dashboard usage."""

    account_id: int
    account_name: str
    avito_user_id: str | None = None
    is_active: bool
    last_inbox_sync_at: datetime | None = None
    last_inbox_sync_status: str | None = None
    last_inbox_error: str | None = None
    chat_count: int = 0
    message_count: int = 0


class DashboardSummaryRead(BaseModel):
    """Top-level summary for the inbox dashboard."""

    total_accounts: int = 0
    active_accounts: int = 0
    total_chats: int = 0
    total_messages: int = 0
    total_clients: int = 0
    total_listings: int = 0
    accounts: tuple[SyncAccountSummary, ...] = Field(default_factory=tuple)
