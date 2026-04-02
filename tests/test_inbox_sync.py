from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import AvitoAccount, AvitoChat, AvitoClient, AvitoListingRef, AvitoMessage
from app.inbox import InboxService, InboxSyncError, InboxSyncResult, sync_account_inbox


class FakeMessengerClient:
    def __init__(
        self,
        *,
        chats: tuple[dict, ...],
        messages_by_chat_id: dict[str, tuple[dict, ...]],
    ) -> None:
        self._chats = chats
        self._messages_by_chat_id = messages_by_chat_id
        self.closed = False

    def get_chats(
        self,
        user_id: str | int,
        *,
        item_ids: tuple[str | int, ...] | None = None,
        unread_only: bool | None = None,
        chat_types: tuple[str, ...] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[dict, ...]:
        del user_id, item_ids, unread_only, chat_types
        return self._chats[offset : offset + limit]

    def get_messages(
        self,
        user_id: str | int,
        chat_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[dict, ...]:
        del user_id
        return self._messages_by_chat_id.get(chat_id, ())[offset : offset + limit]

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )
    try:
        yield factory
    finally:
        engine.dispose()


def _create_account(
    session_factory: sessionmaker[Session],
    *,
    name: str,
    client_id: str,
    avito_user_id: str | None,
    is_active: bool = True,
) -> AvitoAccount:
    with session_factory() as session:
        account = AvitoAccount(
            name=name,
            client_id=client_id,
            client_secret=f"{client_id}-secret",
            avito_user_id=avito_user_id,
            is_active=is_active,
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        return account


def _build_fake_client() -> FakeMessengerClient:
    return FakeMessengerClient(
        chats=(
            {
                "id": "chat-1",
                "created": 1712023200,
                "updated": 1712026800,
                "context": {
                    "type": "item",
                    "value": {
                        "id": 1768287444,
                        "title": "Mazda 3 2008",
                        "url": "https://avito.ru/item/1768287444",
                        "price_string": "300 000 RUB",
                        "status_id": 10,
                        "user_id": 1001,
                        "images": {
                            "main": {
                                "140x105": "https://example.test/item-140x105.jpg",
                            },
                        },
                    },
                },
                "users": [
                    {"id": 1001, "name": "Seller"},
                    {
                        "id": 2002,
                        "name": "Buyer",
                        "public_user_profile": {
                            "url": "https://avito.ru/user/buyer/profile",
                            "avatar": {
                                "default": "https://example.test/avatar.png",
                            },
                        },
                    },
                ],
                "last_message": {
                    "id": "message-2",
                    "created": 1712026800,
                    "direction": "out",
                    "type": "text",
                    "content": {"text": "Hi"},
                },
            },
        ),
        messages_by_chat_id={
            "chat-1": (
                {
                    "id": "message-1",
                    "author_id": 2002,
                    "direction": "in",
                    "type": "text",
                    "created": 1712023200,
                    "is_read": True,
                    "read": 1712023260,
                    "content": {"text": "Hello"},
                },
                {
                    "id": "message-2",
                    "author_id": 1001,
                    "direction": "out",
                    "type": "text",
                    "created": 1712026800,
                    "is_read": True,
                    "read": 1712026860,
                    "content": {"text": "Hi"},
                    "quote": {
                        "id": "message-1",
                        "author_id": 2002,
                        "created": 1712023200,
                        "type": "text",
                        "content": {"text": "Hello"},
                    },
                },
            )
        },
    )


def test_sync_account_inbox_runs_end_to_end_and_is_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    account = _create_account(
        session_factory,
        name="Store A",
        client_id="store-a",
        avito_user_id="1001",
    )
    fake_client = _build_fake_client()
    provider_calls: list[int] = []

    def access_token_provider(current_account: AvitoAccount) -> str:
        provider_calls.append(current_account.id)
        return "access-token"

    def messenger_client_factory(access_token: str) -> FakeMessengerClient:
        assert access_token == "access-token"
        return fake_client

    first_result = sync_account_inbox(
        account.id,
        session_factory=session_factory,
        access_token_provider=access_token_provider,
        messenger_client_factory=messenger_client_factory,
    )
    second_result = sync_account_inbox(
        account.id,
        session_factory=session_factory,
        access_token_provider=access_token_provider,
        messenger_client_factory=messenger_client_factory,
    )

    assert isinstance(first_result, InboxSyncResult)
    assert first_result.status == "success"
    assert first_result.chats_synced == 1
    assert first_result.messages_synced == 2
    assert first_result.clients_synced == 1
    assert first_result.listings_synced == 1
    assert second_result.status == "success"
    assert provider_calls == [account.id, account.id]
    assert fake_client.closed is True

    with session_factory() as session:
        refreshed_account = session.get(AvitoAccount, account.id)
        assert refreshed_account is not None
        assert refreshed_account.last_inbox_sync_status == "success"
        assert refreshed_account.last_inbox_error is None
        assert refreshed_account.last_inbox_sync_at is not None

        assert session.scalar(select(func.count()).select_from(AvitoChat)) == 1
        assert session.scalar(select(func.count()).select_from(AvitoClient)) == 1
        assert session.scalar(select(func.count()).select_from(AvitoListingRef)) == 1
        assert session.scalar(select(func.count()).select_from(AvitoMessage)) == 2


def test_sync_account_inbox_updates_account_error_state_on_failure(
    session_factory: sessionmaker[Session],
) -> None:
    account = _create_account(
        session_factory,
        name="Store A",
        client_id="store-a",
        avito_user_id=None,
    )

    with pytest.raises(InboxSyncError) as error:
        sync_account_inbox(account.id, session_factory=session_factory)

    assert error.value.code == "avito_user_id_missing"

    with session_factory() as session:
        refreshed_account = session.get(AvitoAccount, account.id)
        assert refreshed_account is not None
        assert refreshed_account.last_inbox_sync_status == "error"
        assert refreshed_account.last_inbox_sync_at is not None
        assert "avito_user_id" in (refreshed_account.last_inbox_error or "")


def test_inbox_service_exposes_dashboard_and_read_facade(
    session_factory: sessionmaker[Session],
) -> None:
    account = _create_account(
        session_factory,
        name="Store A",
        client_id="store-a",
        avito_user_id="1001",
    )
    fake_client = _build_fake_client()

    service = InboxService(
        session_factory=session_factory,
        access_token_provider=lambda _: "access-token",
        messenger_client_factory=lambda _: fake_client,
    )

    sync_result = service.sync_account_inbox(account.id)
    chats = service.list_chats(account_id=account.id)
    clients = service.list_clients(account_id=account.id)
    listings = service.list_listings(account_id=account.id)
    messages = service.list_messages(account_id=account.id)
    details = service.get_chat_details(chat_id=chats[0].id, account_id=account.id)
    dashboard = service.get_dashboard_summary()

    assert sync_result.status == "success"
    assert len(chats) == 1
    assert len(clients) == 1
    assert len(listings) == 1
    assert len(messages) == 2
    assert details is not None
    assert details.chat.external_chat_id == "chat-1"
    assert details.client is not None
    assert details.client.external_user_id == "2002"
    assert dashboard.total_accounts == 1
    assert dashboard.active_accounts == 1
    assert dashboard.total_chats == 1
    assert dashboard.total_messages == 2
    assert dashboard.total_clients == 1
    assert dashboard.total_listings == 1
    assert len(dashboard.accounts) == 1
    assert dashboard.accounts[0].account_id == account.id
    assert dashboard.accounts[0].chat_count == 1
    assert dashboard.accounts[0].message_count == 2
