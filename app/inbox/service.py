"""Service facade for inbox read operations and sync orchestration."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AvitoAccount,
    AvitoChat,
    AvitoClient,
    AvitoListingRef,
    AvitoMessage,
)
from app.db.session import get_session_factory
from app.inbox.repository import InboxRepository
from app.inbox.schemas import (
    AvitoChatRead,
    AvitoClientRead,
    AvitoListingRead,
    AvitoMessageRead,
    ChatDetailsRead,
    DashboardSummaryRead,
    SyncAccountSummary,
)
from app.inbox.sync import (
    AccessTokenProvider,
    InboxSyncResult,
    MessengerClientFactory,
    sync_account_inbox as run_inbox_sync,
)


class InboxService:
    """Facade for inbox reads and end-to-end sync orchestration."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
        repository: InboxRepository | None = None,
        access_token_provider: AccessTokenProvider | None = None,
        messenger_client_factory: MessengerClientFactory | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()
        self._repository = repository or InboxRepository(session_factory=self._session_factory)
        self._access_token_provider = access_token_provider
        self._messenger_client_factory = messenger_client_factory

    def sync_account_inbox(
        self,
        account_id: int,
        *,
        page_limit: int = 100,
    ) -> InboxSyncResult:
        """Run one inbox sync for one account."""
        return run_inbox_sync(
            account_id,
            session_factory=self._session_factory,
            repository=self._repository,
            access_token_provider=self._access_token_provider,
            messenger_client_factory=self._messenger_client_factory,
            page_limit=page_limit,
        )

    def list_chats(
        self,
        *,
        account_id: int | None = None,
        chat_type: str | None = None,
        has_listing: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[AvitoChatRead, ...]:
        """List chats for the inbox UI."""
        return self._repository.list_chats(
            account_id=account_id,
            chat_type=chat_type,
            has_listing=has_listing,
            limit=limit,
            offset=offset,
        )

    def list_messages(
        self,
        *,
        chat_id: int | None = None,
        account_id: int | None = None,
        direction: str | None = None,
        message_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[AvitoMessageRead, ...]:
        """List messages for one account or chat."""
        return self._repository.list_messages(
            chat_id=chat_id,
            account_id=account_id,
            direction=direction,
            message_type=message_type,
            limit=limit,
            offset=offset,
        )

    def get_chat(
        self,
        *,
        chat_id: int,
        account_id: int | None = None,
    ) -> AvitoChatRead | None:
        """Return one chat summary."""
        return self._repository.get_chat(chat_id=chat_id, account_id=account_id)

    def get_chat_details(
        self,
        *,
        chat_id: int,
        account_id: int | None = None,
        message_limit: int | None = None,
    ) -> ChatDetailsRead | None:
        """Return one chat with related entities."""
        return self._repository.get_chat_details(
            chat_id=chat_id,
            account_id=account_id,
            message_limit=message_limit,
        )

    def list_clients(
        self,
        *,
        account_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[AvitoClientRead, ...]:
        """List known clients."""
        return self._repository.list_clients(
            account_id=account_id,
            limit=limit,
            offset=offset,
        )

    def list_listings(
        self,
        *,
        account_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[AvitoListingRead, ...]:
        """List known listing references."""
        return self._repository.list_listings(
            account_id=account_id,
            limit=limit,
            offset=offset,
        )

    def get_dashboard_summary(self) -> DashboardSummaryRead:
        """Return aggregated dashboard counters and per-account sync summary."""
        with self._session_factory() as session:
            accounts = tuple(
                session.execute(
                    select(AvitoAccount).order_by(AvitoAccount.id)
                ).scalars()
            )
            chat_counts = dict(
                session.execute(
                    select(AvitoChat.account_id, func.count(AvitoChat.id))
                    .group_by(AvitoChat.account_id)
                ).all()
            )
            message_counts = dict(
                session.execute(
                    select(AvitoMessage.account_id, func.count(AvitoMessage.id))
                    .group_by(AvitoMessage.account_id)
                ).all()
            )

            account_summaries = tuple(
                SyncAccountSummary(
                    account_id=account.id,
                    account_name=account.name,
                    avito_user_id=account.avito_user_id,
                    is_active=account.is_active,
                    last_inbox_sync_at=account.last_inbox_sync_at,
                    last_inbox_sync_status=account.last_inbox_sync_status,
                    last_inbox_error=account.last_inbox_error,
                    chat_count=int(chat_counts.get(account.id, 0)),
                    message_count=int(message_counts.get(account.id, 0)),
                )
                for account in accounts
            )

            total_accounts = len(accounts)
            active_accounts = sum(1 for account in accounts if account.is_active)
            total_chats = int(session.scalar(select(func.count(AvitoChat.id))) or 0)
            total_messages = int(session.scalar(select(func.count(AvitoMessage.id))) or 0)
            total_clients = int(session.scalar(select(func.count(AvitoClient.id))) or 0)
            total_listings = int(session.scalar(select(func.count(AvitoListingRef.id))) or 0)

        return DashboardSummaryRead(
            total_accounts=total_accounts,
            active_accounts=active_accounts,
            total_chats=total_chats,
            total_messages=total_messages,
            total_clients=total_clients,
            total_listings=total_listings,
            accounts=account_summaries,
        )
