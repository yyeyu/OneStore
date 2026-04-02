"""Sync orchestration for the Module 2 inbox data slice."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AvitoAccount
from app.db.session import get_session_factory
from app.inbox.client import AvitoMessengerClient
from app.inbox.normalize import normalize_chat, normalize_messages
from app.inbox.repository import InboxRepository


@dataclass(frozen=True, slots=True)
class InboxSyncResult:
    """Summary of one inbox sync attempt."""

    account_id: int
    account_name: str
    synced_at: datetime
    status: str
    last_error: str | None
    chats_synced: int
    messages_synced: int
    clients_synced: int
    listings_synced: int


class InboxSyncError(RuntimeError):
    """Raised when one inbox sync attempt cannot complete."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


type AccessTokenProvider = Callable[[AvitoAccount], str]
type MessengerClientFactory = Callable[[str], AvitoMessengerClient]


def fetch_access_token_for_account(account: AvitoAccount) -> str:
    """Fetch a short-lived Avito API token for one account."""
    with httpx.Client(base_url="https://api.avito.ru", timeout=20.0) as client:
        response = client.post(
            "/token",
            data={
                "grant_type": "client_credentials",
                "client_id": account.client_id,
                "client_secret": account.client_secret,
            },
            headers={"Accept": "application/json"},
        )

    if response.is_error:
        raise InboxSyncError(
            "token_request_failed",
            (
                f"Failed to fetch Avito access token for account '{account.id}': "
                f"{response.status_code} {response.text[:500]}"
            ),
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise InboxSyncError(
            "token_response_invalid",
            "Avito token response is not valid JSON.",
        ) from exc

    if not isinstance(payload, dict):
        raise InboxSyncError(
            "token_response_invalid",
            "Avito token response must be a JSON object.",
        )

    access_token = str(payload.get("access_token", "")).strip()
    if not access_token:
        raise InboxSyncError(
            "token_missing",
            "Avito token response does not contain access_token.",
        )
    return access_token


def sync_account_inbox(
    account_id: int,
    *,
    session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
    repository: InboxRepository | None = None,
    access_token_provider: AccessTokenProvider | None = None,
    messenger_client_factory: MessengerClientFactory | None = None,
    page_limit: int = 100,
) -> InboxSyncResult:
    """Run one end-to-end inbox sync for the given account id."""
    current_session_factory = session_factory or get_session_factory()
    inbox_repository = repository or InboxRepository(session_factory=current_session_factory)
    token_provider = access_token_provider or fetch_access_token_for_account
    client_factory = messenger_client_factory or _build_messenger_client
    synchronized_at = datetime.now(UTC)

    try:
        account = _load_account(current_session_factory, account_id=account_id)
        if not account.is_active:
            raise InboxSyncError(
                "account_inactive",
                f"Account '{account_id}' is inactive.",
            )
        if not account.avito_user_id:
            raise InboxSyncError(
                "avito_user_id_missing",
                f"Account '{account_id}' does not have avito_user_id configured.",
            )

        access_token = token_provider(account)
        messenger_client = client_factory(access_token)

        try:
            chat_payloads = _collect_chat_payloads(
                messenger_client,
                user_id=account.avito_user_id,
                page_limit=page_limit,
            )

            client_external_ids: set[str] = set()
            listing_external_ids: set[str] = set()
            message_external_ids: set[str] = set()

            for chat_payload in chat_payloads:
                normalized_bundle = normalize_chat(
                    chat_payload,
                    account_user_id=account.avito_user_id,
                )

                client_id = None
                if normalized_bundle.client is not None:
                    synced_client = inbox_repository.upsert_client(
                        account_id=account.id,
                        external_user_id=normalized_bundle.client.external_user_id,
                        display_name=normalized_bundle.client.display_name,
                        profile_url=normalized_bundle.client.profile_url,
                        avatar_url=normalized_bundle.client.avatar_url,
                    )
                    client_id = synced_client.id
                    client_external_ids.add(synced_client.external_user_id)

                listing_id = None
                if normalized_bundle.listing is not None:
                    synced_listing = inbox_repository.upsert_listing(
                        account_id=account.id,
                        external_item_id=normalized_bundle.listing.external_item_id,
                        title=normalized_bundle.listing.title,
                        url=normalized_bundle.listing.url,
                        price_string=normalized_bundle.listing.price_string,
                        status_id=normalized_bundle.listing.status_id,
                        owner_external_user_id=normalized_bundle.listing.owner_external_user_id,
                        image_url=normalized_bundle.listing.image_url,
                    )
                    listing_id = synced_listing.id
                    listing_external_ids.add(synced_listing.external_item_id)

                message_payloads = _collect_message_payloads(
                    messenger_client,
                    user_id=account.avito_user_id,
                    chat_id=normalized_bundle.chat.external_chat_id,
                    page_limit=page_limit,
                )
                normalized_messages = normalize_messages(message_payloads)

                synced_chat = inbox_repository.upsert_chat(
                    account_id=account.id,
                    external_chat_id=normalized_bundle.chat.external_chat_id,
                    chat_type=normalized_bundle.chat.chat_type,
                    client_id=client_id,
                    listing_id=listing_id,
                    external_created_at=normalized_bundle.chat.external_created_at,
                    external_updated_at=normalized_bundle.chat.external_updated_at,
                    last_message_at=normalized_bundle.chat.last_message_at,
                    last_message_id=normalized_bundle.chat.last_message_id,
                    last_message_direction=normalized_bundle.chat.last_message_direction,
                    last_message_type=normalized_bundle.chat.last_message_type,
                    message_count=len(normalized_messages),
                )

                for normalized_message in normalized_messages:
                    synced_message = inbox_repository.upsert_message(
                        account_id=account.id,
                        chat_id=synced_chat.id,
                        external_message_id=normalized_message.external_message_id,
                        author_external_id=normalized_message.author_external_id,
                        direction=normalized_message.direction,
                        message_type=normalized_message.message_type,
                        text=normalized_message.text,
                        content_json=normalized_message.content_json,
                        quote_json=normalized_message.quote_json,
                        is_read=normalized_message.is_read,
                        read_at=normalized_message.read_at,
                        external_created_at=normalized_message.external_created_at,
                    )
                    message_external_ids.add(synced_message.external_message_id)
        finally:
            close_client = getattr(messenger_client, "close", None)
            if callable(close_client):
                close_client()

        _update_account_sync_state(
            current_session_factory,
            account_id=account.id,
            synced_at=synchronized_at,
            status="success",
            error_message=None,
        )
        return InboxSyncResult(
            account_id=account.id,
            account_name=account.name,
            synced_at=synchronized_at,
            status="success",
            last_error=None,
            chats_synced=len(chat_payloads),
            messages_synced=len(message_external_ids),
            clients_synced=len(client_external_ids),
            listings_synced=len(listing_external_ids),
        )
    except Exception as exc:
        _update_account_sync_state(
            current_session_factory,
            account_id=account_id,
            synced_at=synchronized_at,
            status="error",
            error_message=str(exc),
        )
        raise


def _build_messenger_client(access_token: str) -> AvitoMessengerClient:
    return AvitoMessengerClient(access_token)


def _load_account(
    session_factory: sessionmaker[Session] | Callable[[], Session],
    *,
    account_id: int,
) -> AvitoAccount:
    with session_factory() as session:
        account = session.get(AvitoAccount, account_id)
        if account is None:
            raise InboxSyncError(
                "account_not_found",
                f"Account '{account_id}' does not exist.",
            )
        session.expunge(account)
        return account


def _update_account_sync_state(
    session_factory: sessionmaker[Session] | Callable[[], Session],
    *,
    account_id: int,
    synced_at: datetime,
    status: str,
    error_message: str | None,
) -> None:
    with session_factory() as session:
        account = session.get(AvitoAccount, account_id)
        if account is None:
            return
        account.last_inbox_sync_at = synced_at
        account.last_inbox_sync_status = status
        account.last_inbox_error = error_message
        session.add(account)
        session.commit()


def _collect_chat_payloads(
    messenger_client: AvitoMessengerClient,
    *,
    user_id: str,
    page_limit: int,
) -> tuple[dict, ...]:
    chat_payloads: list[dict] = []
    offset = 0

    while True:
        page = messenger_client.get_chats(
            user_id,
            chat_types=("u2i", "u2u"),
            limit=page_limit,
            offset=offset,
        )
        chat_payloads.extend(page)
        if len(page) < page_limit:
            break
        offset += page_limit
        if offset > 1000:
            break

    return tuple(chat_payloads)


def _collect_message_payloads(
    messenger_client: AvitoMessengerClient,
    *,
    user_id: str,
    chat_id: str,
    page_limit: int,
) -> tuple[dict, ...]:
    message_payloads: list[dict] = []
    offset = 0

    while True:
        page = messenger_client.get_messages(
            user_id,
            chat_id,
            limit=page_limit,
            offset=offset,
        )
        message_payloads.extend(page)
        if len(page) < page_limit:
            break
        offset += page_limit
        if offset > 1000:
            break

    return tuple(message_payloads)
