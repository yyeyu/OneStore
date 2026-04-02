"""Database access layer for the Module 2 inbox data slice."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.db.models import (
    AvitoAccount,
    AvitoChat,
    AvitoClient,
    AvitoListingRef,
    AvitoMessage,
)
from app.db.session import get_session_factory
from app.inbox.schemas import (
    AvitoChatRead,
    AvitoClientRead,
    AvitoListingRead,
    AvitoMessageRead,
    ChatDetailsRead,
)


class InboxRepositoryError(ValueError):
    """Raised when inbox repository operations cannot complete."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class InboxRepository:
    """Read/write repository for inbox domain tables."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
    ):
        self._session_factory = session_factory or get_session_factory()

    def upsert_chat(
        self,
        *,
        account_id: int,
        external_chat_id: str,
        chat_type: str,
        client_id: int | None = None,
        listing_id: int | None = None,
        external_created_at: datetime,
        external_updated_at: datetime,
        last_message_at: datetime | None = None,
        last_message_id: str | None = None,
        last_message_direction: str | None = None,
        last_message_type: str | None = None,
        message_count: int | None = None,
    ) -> AvitoChatRead:
        """Create or update one inbox chat row."""
        normalized_external_chat_id = self._normalize_non_empty(
            external_chat_id,
            field="external_chat_id",
        )
        normalized_chat_type = self._normalize_non_empty(chat_type, field="chat_type")
        normalized_last_message_id = self._normalize_optional_non_empty(
            last_message_id,
            field="last_message_id",
        )
        normalized_last_message_direction = self._normalize_optional_non_empty(
            last_message_direction,
            field="last_message_direction",
        )
        normalized_last_message_type = self._normalize_optional_non_empty(
            last_message_type,
            field="last_message_type",
        )
        normalized_message_count = self._normalize_optional_non_negative_int(
            message_count,
            field="message_count",
        )

        with self._session_factory() as session:
            self._get_account_or_raise(session, account_id=account_id)
            if client_id is not None:
                self._get_client_or_raise(
                    session,
                    client_id=client_id,
                    account_id=account_id,
                )
            if listing_id is not None:
                self._get_listing_or_raise(
                    session,
                    listing_id=listing_id,
                    account_id=account_id,
                )

            chat = session.execute(
                select(AvitoChat).where(
                    AvitoChat.account_id == account_id,
                    AvitoChat.external_chat_id == normalized_external_chat_id,
                )
            ).scalar_one_or_none()
            if chat is None:
                chat = AvitoChat(
                    account_id=account_id,
                    external_chat_id=normalized_external_chat_id,
                    chat_type=normalized_chat_type,
                    external_created_at=external_created_at,
                    external_updated_at=external_updated_at,
                )

            chat.chat_type = normalized_chat_type
            chat.client_id = client_id
            chat.listing_id = listing_id
            chat.external_created_at = external_created_at
            chat.external_updated_at = external_updated_at
            chat.last_message_at = last_message_at
            chat.last_message_id = normalized_last_message_id
            chat.last_message_direction = normalized_last_message_direction
            chat.last_message_type = normalized_last_message_type
            chat.message_count = normalized_message_count

            session.add(chat)
            session.commit()
            session.refresh(chat)
            return self._build_chat_read(chat)

    def upsert_message(
        self,
        *,
        account_id: int,
        chat_id: int,
        external_message_id: str,
        author_external_id: str | None = None,
        direction: str,
        message_type: str,
        text: str | None = None,
        content_json: dict[str, Any],
        quote_json: dict[str, Any] | None = None,
        is_read: bool | None = None,
        read_at: datetime | None = None,
        external_created_at: datetime,
    ) -> AvitoMessageRead:
        """Create or update one inbox message row."""
        normalized_external_message_id = self._normalize_non_empty(
            external_message_id,
            field="external_message_id",
        )
        normalized_author_external_id = self._normalize_optional_non_empty(
            author_external_id,
            field="author_external_id",
        )
        normalized_direction = self._normalize_non_empty(direction, field="direction")
        normalized_message_type = self._normalize_non_empty(
            message_type,
            field="message_type",
        )
        normalized_text = self._normalize_optional_text(text)
        normalized_content_json = self._normalize_json_payload(
            content_json,
            field="content_json",
            required=True,
        )
        normalized_quote_json = self._normalize_json_payload(
            quote_json,
            field="quote_json",
            required=False,
        )

        with self._session_factory() as session:
            self._get_account_or_raise(session, account_id=account_id)
            self._get_chat_or_raise(session, chat_id=chat_id, account_id=account_id)

            message = session.execute(
                select(AvitoMessage).where(
                    AvitoMessage.account_id == account_id,
                    AvitoMessage.external_message_id == normalized_external_message_id,
                )
            ).scalar_one_or_none()
            if message is None:
                message = AvitoMessage(
                    account_id=account_id,
                    chat_id=chat_id,
                    external_message_id=normalized_external_message_id,
                    direction=normalized_direction,
                    message_type=normalized_message_type,
                    content_json=normalized_content_json,
                    external_created_at=external_created_at,
                )

            message.chat_id = chat_id
            message.author_external_id = normalized_author_external_id
            message.direction = normalized_direction
            message.message_type = normalized_message_type
            message.text = normalized_text
            message.content_json = normalized_content_json
            message.quote_json = normalized_quote_json
            message.is_read = is_read
            message.read_at = read_at
            message.external_created_at = external_created_at

            session.add(message)
            session.commit()
            session.refresh(message)
            return self._build_message_read(message)

    def upsert_client(
        self,
        *,
        account_id: int,
        external_user_id: str,
        display_name: str | None = None,
        profile_url: str | None = None,
        avatar_url: str | None = None,
    ) -> AvitoClientRead:
        """Create or update one client row."""
        normalized_external_user_id = self._normalize_non_empty(
            external_user_id,
            field="external_user_id",
        )
        normalized_display_name = self._normalize_optional_non_empty(
            display_name,
            field="display_name",
        )
        normalized_profile_url = self._normalize_optional_text(profile_url)
        normalized_avatar_url = self._normalize_optional_text(avatar_url)

        with self._session_factory() as session:
            self._get_account_or_raise(session, account_id=account_id)
            client = session.execute(
                select(AvitoClient).where(
                    AvitoClient.account_id == account_id,
                    AvitoClient.external_user_id == normalized_external_user_id,
                )
            ).scalar_one_or_none()
            if client is None:
                client = AvitoClient(
                    account_id=account_id,
                    external_user_id=normalized_external_user_id,
                )

            client.display_name = normalized_display_name
            client.profile_url = normalized_profile_url
            client.avatar_url = normalized_avatar_url

            session.add(client)
            session.commit()
            session.refresh(client)
            return self._build_client_read(client)

    def upsert_listing(
        self,
        *,
        account_id: int,
        external_item_id: str,
        title: str | None = None,
        url: str | None = None,
        price_string: str | None = None,
        status_id: str | None = None,
        owner_external_user_id: str | None = None,
        image_url: str | None = None,
    ) -> AvitoListingRead:
        """Create or update one listing reference row."""
        normalized_external_item_id = self._normalize_non_empty(
            external_item_id,
            field="external_item_id",
        )
        normalized_title = self._normalize_optional_non_empty(title, field="title")
        normalized_url = self._normalize_optional_text(url)
        normalized_price_string = self._normalize_optional_non_empty(
            price_string,
            field="price_string",
        )
        normalized_status_id = self._normalize_optional_non_empty(
            status_id,
            field="status_id",
        )
        normalized_owner_external_user_id = self._normalize_optional_non_empty(
            owner_external_user_id,
            field="owner_external_user_id",
        )
        normalized_image_url = self._normalize_optional_text(image_url)

        with self._session_factory() as session:
            self._get_account_or_raise(session, account_id=account_id)
            listing = session.execute(
                select(AvitoListingRef).where(
                    AvitoListingRef.account_id == account_id,
                    AvitoListingRef.external_item_id == normalized_external_item_id,
                )
            ).scalar_one_or_none()
            if listing is None:
                listing = AvitoListingRef(
                    account_id=account_id,
                    external_item_id=normalized_external_item_id,
                )

            listing.title = normalized_title
            listing.url = normalized_url
            listing.price_string = normalized_price_string
            listing.status_id = normalized_status_id
            listing.owner_external_user_id = normalized_owner_external_user_id
            listing.image_url = normalized_image_url

            session.add(listing)
            session.commit()
            session.refresh(listing)
            return self._build_listing_read(listing)

    def get_chat(
        self,
        *,
        chat_id: int,
        account_id: int | None = None,
    ) -> AvitoChatRead | None:
        """Return one chat summary by id."""
        with self._session_factory() as session:
            query = select(AvitoChat).where(AvitoChat.id == chat_id)
            if account_id is not None:
                query = query.where(AvitoChat.account_id == account_id)
            chat = session.execute(query).scalar_one_or_none()
            if chat is None:
                return None
            return self._build_chat_read(chat)

    def get_chat_details(
        self,
        *,
        chat_id: int,
        account_id: int | None = None,
        message_limit: int | None = None,
    ) -> ChatDetailsRead | None:
        """Return one chat with related entities and ordered messages."""
        with self._session_factory() as session:
            query = (
                select(AvitoChat)
                .options(joinedload(AvitoChat.client), joinedload(AvitoChat.listing))
                .where(AvitoChat.id == chat_id)
            )
            if account_id is not None:
                query = query.where(AvitoChat.account_id == account_id)

            chat = session.execute(query).unique().scalar_one_or_none()
            if chat is None:
                return None

            messages_query = (
                select(AvitoMessage)
                .where(AvitoMessage.chat_id == chat.id)
                .order_by(AvitoMessage.external_created_at, AvitoMessage.id)
            )
            if message_limit is not None:
                normalized_message_limit = self._normalize_non_negative_int(
                    message_limit,
                    field="message_limit",
                )
                messages_query = messages_query.limit(normalized_message_limit)

            messages = tuple(
                self._build_message_read(message)
                for message in session.execute(messages_query).scalars()
            )
            return ChatDetailsRead(
                chat=self._build_chat_read(chat),
                client=(
                    self._build_client_read(chat.client)
                    if chat.client is not None
                    else None
                ),
                listing=(
                    self._build_listing_read(chat.listing)
                    if chat.listing is not None
                    else None
                ),
                messages=messages,
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
        """List chats ordered for inbox display."""
        normalized_limit = self._normalize_non_negative_int(limit, field="limit")
        normalized_offset = self._normalize_non_negative_int(offset, field="offset")
        normalized_chat_type = self._normalize_optional_non_empty(
            chat_type,
            field="chat_type",
        )

        with self._session_factory() as session:
            query = select(AvitoChat)
            if account_id is not None:
                query = query.where(AvitoChat.account_id == account_id)
            if normalized_chat_type is not None:
                query = query.where(AvitoChat.chat_type == normalized_chat_type)
            if has_listing is True:
                query = query.where(AvitoChat.listing_id.is_not(None))
            elif has_listing is False:
                query = query.where(AvitoChat.listing_id.is_(None))
            query = (
                query.order_by(
                    AvitoChat.last_message_at.is_(None),
                    AvitoChat.last_message_at.desc(),
                    AvitoChat.external_updated_at.desc(),
                    AvitoChat.id.desc(),
                )
                .offset(normalized_offset)
                .limit(normalized_limit)
            )
            return tuple(
                self._build_chat_read(chat)
                for chat in session.execute(query).scalars()
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
        """List messages in stable chronological order."""
        normalized_limit = self._normalize_non_negative_int(limit, field="limit")
        normalized_offset = self._normalize_non_negative_int(offset, field="offset")
        normalized_direction = self._normalize_optional_non_empty(
            direction,
            field="direction",
        )
        normalized_message_type = self._normalize_optional_non_empty(
            message_type,
            field="message_type",
        )

        with self._session_factory() as session:
            query = select(AvitoMessage)
            if chat_id is not None:
                query = query.where(AvitoMessage.chat_id == chat_id)
            if account_id is not None:
                query = query.where(AvitoMessage.account_id == account_id)
            if normalized_direction is not None:
                query = query.where(AvitoMessage.direction == normalized_direction)
            if normalized_message_type is not None:
                query = query.where(
                    AvitoMessage.message_type == normalized_message_type
                )
            query = (
                query.order_by(
                    AvitoMessage.external_created_at,
                    AvitoMessage.id,
                )
                .offset(normalized_offset)
                .limit(normalized_limit)
            )
            return tuple(
                self._build_message_read(message)
                for message in session.execute(query).scalars()
            )

    def list_clients(
        self,
        *,
        account_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[AvitoClientRead, ...]:
        """List clients ordered by most recent update."""
        normalized_limit = self._normalize_non_negative_int(limit, field="limit")
        normalized_offset = self._normalize_non_negative_int(offset, field="offset")

        with self._session_factory() as session:
            query = select(AvitoClient)
            if account_id is not None:
                query = query.where(AvitoClient.account_id == account_id)
            query = (
                query.order_by(
                    AvitoClient.updated_at.desc(),
                    AvitoClient.id.desc(),
                )
                .offset(normalized_offset)
                .limit(normalized_limit)
            )
            return tuple(
                self._build_client_read(client)
                for client in session.execute(query).scalars()
            )

    def list_listings(
        self,
        *,
        account_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[AvitoListingRead, ...]:
        """List listing references ordered by most recent update."""
        normalized_limit = self._normalize_non_negative_int(limit, field="limit")
        normalized_offset = self._normalize_non_negative_int(offset, field="offset")

        with self._session_factory() as session:
            query = select(AvitoListingRef)
            if account_id is not None:
                query = query.where(AvitoListingRef.account_id == account_id)
            query = (
                query.order_by(
                    AvitoListingRef.updated_at.desc(),
                    AvitoListingRef.id.desc(),
                )
                .offset(normalized_offset)
                .limit(normalized_limit)
            )
            return tuple(
                self._build_listing_read(listing)
                for listing in session.execute(query).scalars()
            )

    @staticmethod
    def _get_account_or_raise(session: Session, *, account_id: int) -> AvitoAccount:
        account = session.get(AvitoAccount, account_id)
        if account is None:
            raise InboxRepositoryError(
                "account_not_found",
                f"Account '{account_id}' does not exist.",
            )
        return account

    @staticmethod
    def _get_client_or_raise(
        session: Session,
        *,
        client_id: int,
        account_id: int,
    ) -> AvitoClient:
        client = session.get(AvitoClient, client_id)
        if client is None:
            raise InboxRepositoryError(
                "client_not_found",
                f"Client '{client_id}' does not exist.",
            )
        if client.account_id != account_id:
            raise InboxRepositoryError(
                "client_account_mismatch",
                (
                    f"Client '{client_id}' belongs to account '{client.account_id}', "
                    f"not '{account_id}'."
                ),
            )
        return client

    @staticmethod
    def _get_listing_or_raise(
        session: Session,
        *,
        listing_id: int,
        account_id: int,
    ) -> AvitoListingRef:
        listing = session.get(AvitoListingRef, listing_id)
        if listing is None:
            raise InboxRepositoryError(
                "listing_not_found",
                f"Listing '{listing_id}' does not exist.",
            )
        if listing.account_id != account_id:
            raise InboxRepositoryError(
                "listing_account_mismatch",
                (
                    f"Listing '{listing_id}' belongs to account '{listing.account_id}', "
                    f"not '{account_id}'."
                ),
            )
        return listing

    @staticmethod
    def _get_chat_or_raise(
        session: Session,
        *,
        chat_id: int,
        account_id: int,
    ) -> AvitoChat:
        chat = session.get(AvitoChat, chat_id)
        if chat is None:
            raise InboxRepositoryError(
                "chat_not_found",
                f"Chat '{chat_id}' does not exist.",
            )
        if chat.account_id != account_id:
            raise InboxRepositoryError(
                "chat_account_mismatch",
                (
                    f"Chat '{chat_id}' belongs to account '{chat.account_id}', "
                    f"not '{account_id}'."
                ),
            )
        return chat

    @staticmethod
    def _normalize_non_empty(value: str, *, field: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise InboxRepositoryError(
                f"{field}_invalid",
                f"{field} must not be empty.",
            )
        return normalized

    @classmethod
    def _normalize_optional_non_empty(
        cls,
        value: str | None,
        *,
        field: str,
    ) -> str | None:
        if value is None:
            return None
        return cls._normalize_non_empty(value, field=field)

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    @staticmethod
    def _normalize_json_payload(
        value: dict[str, Any] | None,
        *,
        field: str,
        required: bool,
    ) -> dict[str, Any] | None:
        if value is None:
            if required:
                raise InboxRepositoryError(
                    f"{field}_required",
                    f"{field} is required.",
                )
            return None
        return dict(value)

    @staticmethod
    def _normalize_non_negative_int(value: int, *, field: str) -> int:
        if value < 0:
            raise InboxRepositoryError(
                f"{field}_invalid",
                f"{field} must be greater than or equal to zero.",
            )
        return value

    @classmethod
    def _normalize_optional_non_negative_int(
        cls,
        value: int | None,
        *,
        field: str,
    ) -> int | None:
        if value is None:
            return None
        return cls._normalize_non_negative_int(value, field=field)

    @staticmethod
    def _build_client_read(client: AvitoClient) -> AvitoClientRead:
        return AvitoClientRead(
            id=client.id,
            account_id=client.account_id,
            external_user_id=client.external_user_id,
            display_name=client.display_name,
            profile_url=client.profile_url,
            avatar_url=client.avatar_url,
            created_at=client.created_at,
            updated_at=client.updated_at,
        )

    @staticmethod
    def _build_listing_read(listing: AvitoListingRef) -> AvitoListingRead:
        return AvitoListingRead(
            id=listing.id,
            account_id=listing.account_id,
            external_item_id=listing.external_item_id,
            title=listing.title,
            url=listing.url,
            price_string=listing.price_string,
            status_id=listing.status_id,
            owner_external_user_id=listing.owner_external_user_id,
            image_url=listing.image_url,
            created_at=listing.created_at,
            updated_at=listing.updated_at,
        )

    @staticmethod
    def _build_chat_read(chat: AvitoChat) -> AvitoChatRead:
        return AvitoChatRead(
            id=chat.id,
            account_id=chat.account_id,
            external_chat_id=chat.external_chat_id,
            chat_type=chat.chat_type,
            client_id=chat.client_id,
            listing_id=chat.listing_id,
            external_created_at=chat.external_created_at,
            external_updated_at=chat.external_updated_at,
            last_message_at=chat.last_message_at,
            last_message_id=chat.last_message_id,
            last_message_direction=chat.last_message_direction,
            last_message_type=chat.last_message_type,
            message_count=chat.message_count,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )

    @staticmethod
    def _build_message_read(message: AvitoMessage) -> AvitoMessageRead:
        return AvitoMessageRead(
            id=message.id,
            account_id=message.account_id,
            chat_id=message.chat_id,
            external_message_id=message.external_message_id,
            author_external_id=message.author_external_id,
            direction=message.direction,
            message_type=message.message_type,
            text=message.text,
            content_json=dict(message.content_json),
            quote_json=(
                dict(message.quote_json)
                if message.quote_json is not None
                else None
            ),
            is_read=message.is_read,
            read_at=message.read_at,
            external_created_at=message.external_created_at,
            created_at=message.created_at,
        )
