"""View-model builders for the server-rendered admin panel."""

from __future__ import annotations

from app.admin.schemas import (
    AdminAccountRow,
    AdminAccountsView,
    AdminChatDetailsView,
    AdminChatRow,
    AdminChatsView,
    AdminClientRow,
    AdminClientsView,
    AdminDashboardView,
    AdminJobRow,
    AdminListingRow,
    AdminListingsView,
    AdminMessageRow,
    AdminMessagesView,
    AdminSystemView,
)
from app.core.diagnostics import build_system_summary
from app.inbox import InboxService
from app.jobs import list_job_definitions
from app.modules import ModuleOperationsService

INBOX_MODULE_NAME = "module2_inbox"


def build_dashboard_view(
    *,
    inbox_service: InboxService,
    operations_service: ModuleOperationsService,
) -> AdminDashboardView:
    """Assemble the dashboard page model."""
    summary = inbox_service.get_dashboard_summary()
    inbox_enabled_ids = _get_enabled_inbox_account_ids(operations_service)
    latest_sync_at = max(
        (
            account.last_inbox_sync_at
            for account in summary.accounts
            if account.last_inbox_sync_at is not None
        ),
        default=None,
    )
    error_account_count = sum(
        1
        for account in summary.accounts
        if account.last_inbox_sync_status == "error" or account.last_inbox_error
    )
    return AdminDashboardView(
        summary=summary,
        inbox_enabled_accounts=len(inbox_enabled_ids),
        latest_sync_at=latest_sync_at,
        error_account_count=error_account_count,
        accounts=summary.accounts,
    )


def build_accounts_view(
    *,
    operations_service: ModuleOperationsService,
) -> AdminAccountsView:
    """Assemble the accounts page model."""
    accounts = operations_service.list_accounts()
    inbox_enabled_ids = _get_enabled_inbox_account_ids(operations_service)
    rows = tuple(
        AdminAccountRow(
            id=account.id,
            name=account.name,
            avito_user_id=account.avito_user_id,
            is_active=account.is_active,
            module2_inbox_enabled=account.id in inbox_enabled_ids,
            last_inbox_sync_at=account.last_inbox_sync_at,
            last_inbox_sync_status=account.last_inbox_sync_status,
            last_inbox_error=account.last_inbox_error,
            can_sync=(
                account.is_active
                and account.id in inbox_enabled_ids
                and account.avito_user_id is not None
            ),
        )
        for account in accounts
    )
    return AdminAccountsView(
        total_accounts=len(accounts),
        inbox_enabled_accounts=len(inbox_enabled_ids),
        accounts=rows,
    )


def build_chats_view(
    *,
    inbox_service: InboxService,
    operations_service: ModuleOperationsService,
    account_id: int | None = None,
    chat_type: str | None = None,
    has_listing: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AdminChatsView:
    """Assemble the chats list page."""
    accounts = operations_service.list_accounts()
    chats = inbox_service.list_chats(
        account_id=account_id,
        chat_type=chat_type,
        has_listing=has_listing,
        limit=limit,
        offset=offset,
    )
    client_map = {
        client.id: client
        for client in inbox_service.list_clients(
            account_id=account_id,
            limit=max(limit + offset, 1000),
            offset=0,
        )
    }
    listing_map = {
        listing.id: listing
        for listing in inbox_service.list_listings(
            account_id=account_id,
            limit=max(limit + offset, 1000),
            offset=0,
        )
    }
    account_name_map = _build_account_name_map(accounts)
    rows = tuple(
        AdminChatRow(
            id=chat.id,
            account_id=chat.account_id,
            account_name=account_name_map.get(chat.account_id),
            external_chat_id=chat.external_chat_id,
            chat_type=chat.chat_type,
            client_name=(
                client_map[chat.client_id].display_name
                or client_map[chat.client_id].external_user_id
                if chat.client_id in client_map
                else None
            ),
            listing_title=(
                listing_map[chat.listing_id].title
                or listing_map[chat.listing_id].external_item_id
                if chat.listing_id in listing_map
                else None
            ),
            last_message_at=chat.last_message_at,
            last_message_direction=chat.last_message_direction,
            last_message_type=chat.last_message_type,
            message_count=chat.message_count,
        )
        for chat in chats
    )
    return AdminChatsView(
        accounts=accounts,
        account_id=account_id,
        chat_type=chat_type,
        has_listing=has_listing,
        limit=limit,
        offset=offset,
        chats=rows,
    )


def build_chat_details_view(
    *,
    inbox_service: InboxService,
    operations_service: ModuleOperationsService,
    chat_id: int,
    account_id: int | None = None,
) -> AdminChatDetailsView | None:
    """Assemble the chat details page."""
    details = inbox_service.get_chat_details(
        chat_id=chat_id,
        account_id=account_id,
    )
    if details is None:
        return None
    account_name_map = _build_account_name_map(operations_service.list_accounts())
    return AdminChatDetailsView(
        account_name=account_name_map.get(details.chat.account_id),
        details=details,
    )


def build_messages_view(
    *,
    inbox_service: InboxService,
    operations_service: ModuleOperationsService,
    account_id: int | None = None,
    chat_id: int | None = None,
    direction: str | None = None,
    message_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AdminMessagesView:
    """Assemble the messages list page."""
    accounts = operations_service.list_accounts()
    messages = inbox_service.list_messages(
        account_id=account_id,
        chat_id=chat_id,
        direction=direction,
        message_type=message_type,
        limit=limit,
        offset=offset,
    )
    chats = inbox_service.list_chats(
        account_id=account_id,
        limit=max(limit + offset, 1000),
        offset=0,
    )
    chat_map = {chat.id: chat for chat in chats}
    account_name_map = _build_account_name_map(accounts)
    rows = tuple(
        AdminMessageRow(
            account_name=account_name_map.get(message.account_id),
            chat_external_id=(
                chat_map[message.chat_id].external_chat_id
                if message.chat_id in chat_map
                else None
            ),
            message=message,
        )
        for message in messages
    )
    return AdminMessagesView(
        accounts=accounts,
        account_id=account_id,
        chat_id=chat_id,
        direction=direction,
        message_type=message_type,
        limit=limit,
        offset=offset,
        messages=rows,
    )


def build_clients_view(
    *,
    inbox_service: InboxService,
    operations_service: ModuleOperationsService,
    account_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AdminClientsView:
    """Assemble the clients list page."""
    accounts = operations_service.list_accounts()
    account_name_map = _build_account_name_map(accounts)
    rows = tuple(
        AdminClientRow(
            account_name=account_name_map.get(client.account_id),
            client=client,
        )
        for client in inbox_service.list_clients(
            account_id=account_id,
            limit=limit,
            offset=offset,
        )
    )
    return AdminClientsView(
        accounts=accounts,
        account_id=account_id,
        limit=limit,
        offset=offset,
        clients=rows,
    )


def build_listings_view(
    *,
    inbox_service: InboxService,
    operations_service: ModuleOperationsService,
    account_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AdminListingsView:
    """Assemble the listings list page."""
    accounts = operations_service.list_accounts()
    account_name_map = _build_account_name_map(accounts)
    rows = tuple(
        AdminListingRow(
            account_name=account_name_map.get(listing.account_id),
            listing=listing,
        )
        for listing in inbox_service.list_listings(
            account_id=account_id,
            limit=limit,
            offset=offset,
        )
    )
    return AdminListingsView(
        accounts=accounts,
        account_id=account_id,
        limit=limit,
        offset=offset,
        listings=rows,
    )


def build_system_view(
    *,
    operations_service: ModuleOperationsService,
) -> AdminSystemView:
    """Assemble the system page."""
    accounts = operations_service.list_accounts()
    modules = operations_service.list_modules()
    jobs = tuple(
        AdminJobRow(
            name=job.name,
            module_name=job.module_name,
            description=job.description,
            default_interval_seconds=job.default_interval_seconds,
            requires_account=job.requires_account,
            scheduler_enabled=job.scheduler_enabled,
        )
        for job in list_job_definitions()
    )
    return AdminSystemView(
        system=build_system_summary(),
        total_accounts=len(accounts),
        modules=modules,
        jobs=jobs,
    )


def _get_enabled_inbox_account_ids(
    operations_service: ModuleOperationsService,
) -> set[int]:
    return {
        setting.account_id
        for setting in operations_service.list_module_settings(
            module_name=INBOX_MODULE_NAME,
        )
        if setting.is_enabled
    }


def _build_account_name_map(accounts: tuple) -> dict[int, str]:
    return {account.id: account.name for account in accounts}
