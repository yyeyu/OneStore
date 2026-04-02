"""Server-rendered admin view models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.inbox.schemas import (
    AvitoClientRead,
    AvitoListingRead,
    AvitoMessageRead,
    ChatDetailsRead,
    DashboardSummaryRead,
    SyncAccountSummary,
)
from app.modules import AccountSummary, ModuleSummary


class AdminDashboardView(BaseModel):
    """Dashboard metrics and per-account sync state."""

    summary: DashboardSummaryRead
    inbox_enabled_accounts: int = 0
    latest_sync_at: datetime | None = None
    error_account_count: int = 0
    accounts: tuple[SyncAccountSummary, ...] = Field(default_factory=tuple)


class AdminAccountRow(BaseModel):
    """One account row for the admin page."""

    id: int
    name: str
    avito_user_id: str | None = None
    is_active: bool
    module2_inbox_enabled: bool
    last_inbox_sync_at: datetime | None = None
    last_inbox_sync_status: str | None = None
    last_inbox_error: str | None = None
    can_sync: bool


class AdminAccountsView(BaseModel):
    """Accounts page view model."""

    total_accounts: int = 0
    inbox_enabled_accounts: int = 0
    accounts: tuple[AdminAccountRow, ...] = Field(default_factory=tuple)


class AdminChatRow(BaseModel):
    """Chat row with resolved labels for admin rendering."""

    id: int
    account_id: int
    account_name: str | None = None
    external_chat_id: str
    chat_type: str
    client_name: str | None = None
    listing_title: str | None = None
    last_message_at: datetime | None = None
    last_message_direction: str | None = None
    last_message_type: str | None = None
    message_count: int | None = None


class AdminChatsView(BaseModel):
    """Chats page view model."""

    accounts: tuple[AccountSummary, ...] = Field(default_factory=tuple)
    account_id: int | None = None
    chat_type: str | None = None
    has_listing: bool | None = None
    limit: int = 100
    offset: int = 0
    chats: tuple[AdminChatRow, ...] = Field(default_factory=tuple)


class AdminChatDetailsView(BaseModel):
    """Single chat details page model."""

    account_name: str | None = None
    details: ChatDetailsRead


class AdminMessageRow(BaseModel):
    """Message row with resolved account/chat labels."""

    account_name: str | None = None
    chat_external_id: str | None = None
    message: AvitoMessageRead


class AdminMessagesView(BaseModel):
    """Messages page view model."""

    accounts: tuple[AccountSummary, ...] = Field(default_factory=tuple)
    account_id: int | None = None
    chat_id: int | None = None
    direction: str | None = None
    message_type: str | None = None
    limit: int = 100
    offset: int = 0
    messages: tuple[AdminMessageRow, ...] = Field(default_factory=tuple)


class AdminClientRow(BaseModel):
    """Client row with resolved account label."""

    account_name: str | None = None
    client: AvitoClientRead


class AdminClientsView(BaseModel):
    """Clients page view model."""

    accounts: tuple[AccountSummary, ...] = Field(default_factory=tuple)
    account_id: int | None = None
    limit: int = 100
    offset: int = 0
    clients: tuple[AdminClientRow, ...] = Field(default_factory=tuple)


class AdminListingRow(BaseModel):
    """Listing row with resolved account label."""

    account_name: str | None = None
    listing: AvitoListingRead


class AdminListingsView(BaseModel):
    """Listings page view model."""

    accounts: tuple[AccountSummary, ...] = Field(default_factory=tuple)
    account_id: int | None = None
    limit: int = 100
    offset: int = 0
    listings: tuple[AdminListingRow, ...] = Field(default_factory=tuple)


class AdminJobRow(BaseModel):
    """Runtime job registry row for the system page."""

    name: str
    module_name: str
    description: str
    default_interval_seconds: int
    requires_account: bool
    scheduler_enabled: bool


class AdminSystemView(BaseModel):
    """System page view model."""

    system: dict[str, Any]
    total_accounts: int = 0
    modules: tuple[ModuleSummary, ...] = Field(default_factory=tuple)
    jobs: tuple[AdminJobRow, ...] = Field(default_factory=tuple)
