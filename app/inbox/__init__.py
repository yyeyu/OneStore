"""Inbox package exports."""

from app.inbox.client import (
    AvitoMessengerClient,
    AvitoMessengerClientError,
    AvitoRateLimitState,
)
from app.inbox.normalize import (
    InboxNormalizationError,
    NormalizedChat,
    NormalizedChatBundle,
    NormalizedClient,
    NormalizedListing,
    NormalizedMessage,
    extract_client,
    extract_listing,
    normalize_chat,
    normalize_chats,
    normalize_message,
    normalize_messages,
)
from app.inbox.repository import InboxRepository, InboxRepositoryError
from app.inbox.schemas import (
    AvitoChatRead,
    AvitoClientRead,
    AvitoListingRead,
    AvitoMessageRead,
    ChatDetailsRead,
    DashboardSummaryRead,
    SyncAccountSummary,
)
from app.inbox.service import InboxService
from app.inbox.sync import (
    InboxSyncError,
    InboxSyncResult,
    fetch_access_token_for_account,
    sync_account_inbox,
)

__all__ = [
    "AvitoMessengerClient",
    "AvitoMessengerClientError",
    "AvitoChatRead",
    "AvitoClientRead",
    "AvitoListingRead",
    "AvitoMessageRead",
    "AvitoRateLimitState",
    "ChatDetailsRead",
    "DashboardSummaryRead",
    "extract_client",
    "extract_listing",
    "InboxNormalizationError",
    "InboxService",
    "InboxRepository",
    "InboxRepositoryError",
    "InboxSyncError",
    "InboxSyncResult",
    "NormalizedChat",
    "NormalizedChatBundle",
    "NormalizedClient",
    "NormalizedListing",
    "NormalizedMessage",
    "fetch_access_token_for_account",
    "normalize_chat",
    "normalize_chats",
    "normalize_message",
    "normalize_messages",
    "sync_account_inbox",
    "SyncAccountSummary",
]
