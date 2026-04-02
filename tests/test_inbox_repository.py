from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import AvitoAccount
from app.inbox import InboxRepository, InboxRepositoryError


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


@pytest.fixture
def repository(session_factory: sessionmaker[Session]) -> InboxRepository:
    return InboxRepository(session_factory=session_factory)


def _create_account(
    session_factory: sessionmaker[Session],
    *,
    name: str,
    client_id: str,
    avito_user_id: str,
) -> AvitoAccount:
    with session_factory() as session:
        account = AvitoAccount(
            name=name,
            client_id=client_id,
            client_secret=f"{client_id}-secret",
            avito_user_id=avito_user_id,
            is_active=True,
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        return account


def test_upsert_client_and_listing_are_idempotent(
    session_factory: sessionmaker[Session],
    repository: InboxRepository,
) -> None:
    account = _create_account(
        session_factory,
        name="Store A",
        client_id="store-a",
        avito_user_id="1001",
    )

    first_client = repository.upsert_client(
        account_id=account.id,
        external_user_id="client-1",
        display_name="First User",
        profile_url=" https://example.test/users/1 ",
    )
    second_client = repository.upsert_client(
        account_id=account.id,
        external_user_id="client-1",
        display_name=" Updated User ",
        avatar_url="https://example.test/avatar.png",
    )

    assert first_client.id == second_client.id
    assert second_client.display_name == "Updated User"
    assert second_client.profile_url is None
    assert second_client.avatar_url == "https://example.test/avatar.png"

    first_listing = repository.upsert_listing(
        account_id=account.id,
        external_item_id="listing-1",
        title="Listing A",
        price_string="10 000 RUB",
    )
    second_listing = repository.upsert_listing(
        account_id=account.id,
        external_item_id="listing-1",
        title="Listing A Updated",
        url=" https://example.test/items/1 ",
    )

    assert first_listing.id == second_listing.id
    assert second_listing.title == "Listing A Updated"
    assert second_listing.url == "https://example.test/items/1"
    assert second_listing.price_string is None


def test_upsert_chat_message_and_get_chat_details(
    session_factory: sessionmaker[Session],
    repository: InboxRepository,
) -> None:
    account = _create_account(
        session_factory,
        name="Store A",
        client_id="store-a",
        avito_user_id="1001",
    )
    client = repository.upsert_client(
        account_id=account.id,
        external_user_id="client-1",
        display_name="Buyer One",
    )
    listing = repository.upsert_listing(
        account_id=account.id,
        external_item_id="listing-1",
        title="Product One",
    )
    started_at = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)

    chat = repository.upsert_chat(
        account_id=account.id,
        external_chat_id="chat-1",
        chat_type="u2i",
        client_id=client.id,
        listing_id=listing.id,
        external_created_at=started_at,
        external_updated_at=started_at,
    )
    first_message = repository.upsert_message(
        account_id=account.id,
        chat_id=chat.id,
        external_message_id="message-1",
        author_external_id="client-1",
        direction="in",
        message_type="text",
        text="Hello",
        content_json={"text": "Hello"},
        external_created_at=started_at,
    )
    second_message = repository.upsert_message(
        account_id=account.id,
        chat_id=chat.id,
        external_message_id="message-2",
        author_external_id="1001",
        direction="out",
        message_type="text",
        text="Hi",
        content_json={"text": "Hi"},
        quote_json={"message_id": "message-1"},
        is_read=True,
        read_at=started_at + timedelta(minutes=2),
        external_created_at=started_at + timedelta(minutes=1),
    )

    updated_chat = repository.upsert_chat(
        account_id=account.id,
        external_chat_id="chat-1",
        chat_type="u2i",
        client_id=client.id,
        listing_id=listing.id,
        external_created_at=started_at,
        external_updated_at=started_at + timedelta(minutes=1),
        last_message_at=started_at + timedelta(minutes=1),
        last_message_id=second_message.external_message_id,
        last_message_direction=second_message.direction,
        last_message_type=second_message.message_type,
        message_count=2,
    )

    details = repository.get_chat_details(chat_id=chat.id, account_id=account.id)

    assert details is not None
    assert updated_chat.id == chat.id
    assert details.chat.id == updated_chat.id
    assert details.chat.last_message_id == "message-2"
    assert details.client is not None
    assert details.client.display_name == "Buyer One"
    assert details.listing is not None
    assert details.listing.title == "Product One"
    assert [message.external_message_id for message in details.messages] == [
        first_message.external_message_id,
        second_message.external_message_id,
    ]
    assert details.messages[1].quote_json == {"message_id": "message-1"}


def test_upsert_message_is_idempotent_and_updates_json_payloads(
    session_factory: sessionmaker[Session],
    repository: InboxRepository,
) -> None:
    account = _create_account(
        session_factory,
        name="Store A",
        client_id="store-a",
        avito_user_id="1001",
    )
    started_at = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)

    chat = repository.upsert_chat(
        account_id=account.id,
        external_chat_id="chat-1",
        chat_type="u2i",
        external_created_at=started_at,
        external_updated_at=started_at,
    )
    first_message = repository.upsert_message(
        account_id=account.id,
        chat_id=chat.id,
        external_message_id="message-1",
        author_external_id="2002",
        direction="in",
        message_type="text",
        text="Hello",
        content_json={"text": "Hello"},
        quote_json={"id": "quote-0"},
        external_created_at=started_at,
    )
    second_message = repository.upsert_message(
        account_id=account.id,
        chat_id=chat.id,
        external_message_id="message-1",
        author_external_id="2002",
        direction="in",
        message_type="link",
        text="https://example.test",
        content_json={"link": {"url": "https://example.test"}},
        quote_json={"id": "quote-1"},
        is_read=True,
        read_at=started_at + timedelta(minutes=1),
        external_created_at=started_at,
    )

    messages = repository.list_messages(account_id=account.id, chat_id=chat.id)

    assert second_message.id == first_message.id
    assert len(messages) == 1
    assert messages[0].message_type == "link"
    assert messages[0].content_json == {"link": {"url": "https://example.test"}}
    assert messages[0].quote_json == {"id": "quote-1"}
    assert messages[0].is_read is True


def test_list_queries_filter_and_sort_by_account_and_time(
    session_factory: sessionmaker[Session],
    repository: InboxRepository,
) -> None:
    account_one = _create_account(
        session_factory,
        name="Store A",
        client_id="store-a",
        avito_user_id="1001",
    )
    account_two = _create_account(
        session_factory,
        name="Store B",
        client_id="store-b",
        avito_user_id="1002",
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    client_one = repository.upsert_client(
        account_id=account_one.id,
        external_user_id="client-a",
        display_name="Alpha",
    )
    client_two = repository.upsert_client(
        account_id=account_one.id,
        external_user_id="client-b",
        display_name="Beta",
    )
    listing_one = repository.upsert_listing(
        account_id=account_one.id,
        external_item_id="listing-a",
        title="A",
    )
    listing_two = repository.upsert_listing(
        account_id=account_one.id,
        external_item_id="listing-b",
        title="B",
    )

    older_chat = repository.upsert_chat(
        account_id=account_one.id,
        external_chat_id="chat-a",
        chat_type="u2i",
        client_id=client_one.id,
        listing_id=listing_one.id,
        external_created_at=now - timedelta(hours=2),
        external_updated_at=now - timedelta(hours=1),
        last_message_at=now - timedelta(hours=1),
        last_message_id="message-a",
        last_message_direction="in",
        last_message_type="text",
        message_count=1,
    )
    newer_chat = repository.upsert_chat(
        account_id=account_one.id,
        external_chat_id="chat-b",
        chat_type="u2u",
        client_id=client_two.id,
        listing_id=listing_two.id,
        external_created_at=now - timedelta(hours=1),
        external_updated_at=now,
        last_message_at=now,
        last_message_id="message-c",
        last_message_direction="out",
        last_message_type="image",
        message_count=2,
    )
    foreign_chat = repository.upsert_chat(
        account_id=account_two.id,
        external_chat_id="chat-x",
        chat_type="u2i",
        external_created_at=now,
        external_updated_at=now,
    )

    repository.upsert_message(
        account_id=account_one.id,
        chat_id=older_chat.id,
        external_message_id="message-a",
        direction="in",
        message_type="text",
        text="old",
        content_json={"text": "old"},
        external_created_at=now - timedelta(hours=1),
    )
    repository.upsert_message(
        account_id=account_one.id,
        chat_id=newer_chat.id,
        external_message_id="message-b",
        direction="in",
        message_type="text",
        text="new-1",
        content_json={"text": "new-1"},
        external_created_at=now - timedelta(minutes=30),
    )
    repository.upsert_message(
        account_id=account_one.id,
        chat_id=newer_chat.id,
        external_message_id="message-c",
        direction="out",
        message_type="image",
        content_json={"image_url": "https://example.test/image.png"},
        external_created_at=now - timedelta(minutes=5),
    )
    repository.upsert_message(
        account_id=account_two.id,
        chat_id=foreign_chat.id,
        external_message_id="message-x",
        direction="in",
        message_type="text",
        text="foreign",
        content_json={"text": "foreign"},
        external_created_at=now,
    )

    chats = repository.list_chats(account_id=account_one.id)
    listing_chats = repository.list_chats(
        account_id=account_one.id,
        has_listing=True,
    )
    u2u_chats = repository.list_chats(
        account_id=account_one.id,
        chat_type="u2u",
    )
    messages = repository.list_messages(account_id=account_one.id)
    outbound_images = repository.list_messages(
        account_id=account_one.id,
        direction="out",
        message_type="image",
    )
    clients = repository.list_clients(account_id=account_one.id)
    listings = repository.list_listings(account_id=account_one.id)

    assert [chat.external_chat_id for chat in chats] == ["chat-b", "chat-a"]
    assert [chat.external_chat_id for chat in listing_chats] == ["chat-b", "chat-a"]
    assert [chat.external_chat_id for chat in u2u_chats] == ["chat-b"]
    assert [message.external_message_id for message in messages] == [
        "message-a",
        "message-b",
        "message-c",
    ]
    assert [message.external_message_id for message in outbound_images] == ["message-c"]
    assert {client.external_user_id for client in clients} == {"client-a", "client-b"}
    assert {listing.external_item_id for listing in listings} == {"listing-a", "listing-b"}
    assert all(chat.account_id == account_one.id for chat in chats)
    assert all(message.account_id == account_one.id for message in messages)


def test_repository_rejects_cross_account_links(
    session_factory: sessionmaker[Session],
    repository: InboxRepository,
) -> None:
    account_one = _create_account(
        session_factory,
        name="Store A",
        client_id="store-a",
        avito_user_id="1001",
    )
    account_two = _create_account(
        session_factory,
        name="Store B",
        client_id="store-b",
        avito_user_id="1002",
    )
    now = datetime(2026, 4, 2, 14, 0, tzinfo=UTC)

    foreign_client = repository.upsert_client(
        account_id=account_two.id,
        external_user_id="client-foreign",
    )
    foreign_listing = repository.upsert_listing(
        account_id=account_two.id,
        external_item_id="listing-foreign",
    )
    own_chat = repository.upsert_chat(
        account_id=account_one.id,
        external_chat_id="chat-1",
        chat_type="u2i",
        external_created_at=now,
        external_updated_at=now,
    )
    foreign_chat = repository.upsert_chat(
        account_id=account_two.id,
        external_chat_id="chat-2",
        chat_type="u2i",
        external_created_at=now,
        external_updated_at=now,
    )

    with pytest.raises(InboxRepositoryError) as client_error:
        repository.upsert_chat(
            account_id=account_one.id,
            external_chat_id="chat-3",
            chat_type="u2i",
            client_id=foreign_client.id,
            external_created_at=now,
            external_updated_at=now,
        )

    with pytest.raises(InboxRepositoryError) as listing_error:
        repository.upsert_chat(
            account_id=account_one.id,
            external_chat_id="chat-4",
            chat_type="u2i",
            listing_id=foreign_listing.id,
            external_created_at=now,
            external_updated_at=now,
        )

    with pytest.raises(InboxRepositoryError) as message_error:
        repository.upsert_message(
            account_id=account_one.id,
            chat_id=foreign_chat.id,
            external_message_id="message-1",
            direction="in",
            message_type="text",
            content_json={"text": "bad"},
            external_created_at=now,
        )

    assert own_chat.account_id == account_one.id
    assert client_error.value.code == "client_account_mismatch"
    assert listing_error.value.code == "listing_account_mismatch"
    assert message_error.value.code == "chat_account_mismatch"
