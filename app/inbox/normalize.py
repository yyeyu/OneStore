"""Normalization helpers for Avito Messenger payloads."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class InboxNormalizationError(ValueError):
    """Raised when Avito payload normalization fails."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class NormalizedClient:
    """Normalized counterparty representation."""

    external_user_id: str
    display_name: str | None = None
    profile_url: str | None = None
    avatar_url: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedListing:
    """Normalized listing reference representation."""

    external_item_id: str
    title: str | None = None
    url: str | None = None
    price_string: str | None = None
    status_id: str | None = None
    owner_external_user_id: str | None = None
    image_url: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedChat:
    """Normalized chat summary for repository upsert."""

    external_chat_id: str
    chat_type: str
    external_created_at: datetime
    external_updated_at: datetime
    last_message_at: datetime | None = None
    last_message_id: str | None = None
    last_message_direction: str | None = None
    last_message_type: str | None = None
    message_count: int | None = None


@dataclass(frozen=True, slots=True)
class NormalizedChatBundle:
    """Chat plus related normalized entities extracted from one payload."""

    chat: NormalizedChat
    client: NormalizedClient | None = None
    listing: NormalizedListing | None = None


@dataclass(frozen=True, slots=True)
class NormalizedMessage:
    """Normalized message payload for repository upsert."""

    external_message_id: str
    author_external_id: str | None
    direction: str
    message_type: str
    text: str | None
    content_json: dict[str, Any]
    quote_json: dict[str, Any] | None
    is_read: bool | None
    read_at: datetime | None
    external_created_at: datetime


def extract_client(
    users: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    account_user_id: str | int | None,
) -> NormalizedClient | None:
    """Extract counterparty user from chat users."""
    if not users:
        return None

    normalized_account_user_id = _normalize_optional_identifier(account_user_id)
    normalized_users = [_expect_object(user, field="users[]") for user in users]

    selected_user = None
    for user in normalized_users:
        user_id = _extract_user_identifier(user)
        if normalized_account_user_id is None or user_id != normalized_account_user_id:
            selected_user = user
            break

    if selected_user is None and len(normalized_users) == 1:
        selected_user = normalized_users[0]
    if selected_user is None:
        return None

    profile = selected_user.get("public_user_profile")
    profile_object = profile if isinstance(profile, dict) else {}
    return NormalizedClient(
        external_user_id=_extract_user_identifier(selected_user),
        display_name=_normalize_optional_text(selected_user.get("name")),
        profile_url=_normalize_optional_text(profile_object.get("url")),
        avatar_url=_extract_avatar_url(profile_object),
    )


def extract_listing(context: dict[str, Any] | None) -> NormalizedListing | None:
    """Extract listing reference from chat context."""
    if not context:
        return None

    normalized_context = _expect_object(context, field="context")
    value = normalized_context.get("value")
    if not isinstance(value, dict):
        return None

    external_item_id = _normalize_optional_identifier(value.get("id"))
    if external_item_id is None:
        return None

    return NormalizedListing(
        external_item_id=external_item_id,
        title=_normalize_optional_text(value.get("title")),
        url=_normalize_optional_text(value.get("url")),
        price_string=_normalize_optional_text(value.get("price_string")),
        status_id=_normalize_optional_identifier(value.get("status_id")),
        owner_external_user_id=_normalize_optional_identifier(value.get("user_id")),
        image_url=_extract_listing_image_url(value),
    )


def normalize_chat(
    chat_payload: dict[str, Any],
    *,
    account_user_id: str | int | None,
) -> NormalizedChatBundle:
    """Normalize one chat payload returned by the Messenger API."""
    payload = _expect_object(chat_payload, field="chat")
    last_message = payload.get("last_message")
    last_message_object = last_message if isinstance(last_message, dict) else {}

    chat = NormalizedChat(
        external_chat_id=_normalize_required_identifier(payload.get("id"), field="chat.id"),
        # The official chat response currently does not expose chat_type directly,
        # so infer it from the available payload shape.
        chat_type=_infer_chat_type(payload),
        external_created_at=_timestamp_to_datetime(
            payload.get("created"),
            field="chat.created",
        ),
        external_updated_at=_timestamp_to_datetime(
            payload.get("updated"),
            field="chat.updated",
        ),
        last_message_at=_timestamp_to_optional_datetime(last_message_object.get("created")),
        last_message_id=_normalize_optional_identifier(last_message_object.get("id")),
        last_message_direction=_normalize_optional_text(last_message_object.get("direction")),
        last_message_type=_normalize_optional_text(last_message_object.get("type")),
        message_count=None,
    )
    return NormalizedChatBundle(
        chat=chat,
        client=extract_client(
            payload.get("users"),
            account_user_id=account_user_id,
        ),
        listing=extract_listing(payload.get("context")),
    )


def normalize_message(message_payload: dict[str, Any]) -> NormalizedMessage:
    """Normalize one message payload returned by the Messenger API."""
    payload = _expect_object(message_payload, field="message")
    content = _expect_object(payload.get("content"), field="message.content")
    quote = payload.get("quote")

    return NormalizedMessage(
        external_message_id=_normalize_required_identifier(
            payload.get("id"),
            field="message.id",
        ),
        author_external_id=_normalize_optional_identifier(payload.get("author_id")),
        direction=_normalize_required_text(payload.get("direction"), field="message.direction"),
        message_type=_normalize_required_text(payload.get("type"), field="message.type"),
        text=_extract_message_text(content),
        content_json=deepcopy(content),
        quote_json=deepcopy(_expect_object(quote, field="message.quote")) if quote is not None else None,
        is_read=_normalize_optional_bool(payload.get("is_read")),
        read_at=_timestamp_to_optional_datetime(payload.get("read")),
        external_created_at=_timestamp_to_datetime(
            payload.get("created"),
            field="message.created",
        ),
    )


def normalize_chats(
    chat_payloads: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    account_user_id: str | int | None,
) -> tuple[NormalizedChatBundle, ...]:
    """Normalize multiple chat payloads."""
    return tuple(
        normalize_chat(chat_payload, account_user_id=account_user_id)
        for chat_payload in chat_payloads
    )


def normalize_messages(
    message_payloads: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> tuple[NormalizedMessage, ...]:
    """Normalize multiple message payloads."""
    return tuple(normalize_message(message_payload) for message_payload in message_payloads)


def _infer_chat_type(chat_payload: dict[str, Any]) -> str:
    explicit_type = _normalize_optional_text(chat_payload.get("chat_type"))
    if explicit_type in {"u2i", "u2u"}:
        return explicit_type

    explicit_type = _normalize_optional_text(chat_payload.get("type"))
    if explicit_type in {"u2i", "u2u"}:
        return explicit_type

    context = chat_payload.get("context")
    if isinstance(context, dict):
        context_type = _normalize_optional_text(context.get("type"))
        if context_type == "item":
            return "u2i"
        if isinstance(context.get("value"), dict):
            return "u2i"
    return "u2u"


def _extract_message_text(content: dict[str, Any]) -> str | None:
    text = _normalize_optional_text(content.get("text"))
    if text is not None:
        return text

    link = content.get("link")
    if isinstance(link, dict):
        text = _normalize_optional_text(link.get("text"))
        if text is not None:
            return text

    location = content.get("location")
    if isinstance(location, dict):
        text = _normalize_optional_text(location.get("text"))
        if text is not None:
            return text
        text = _normalize_optional_text(location.get("title"))
        if text is not None:
            return text

    item = content.get("item")
    if isinstance(item, dict):
        text = _normalize_optional_text(item.get("title"))
        if text is not None:
            return text

    return None


def _extract_user_identifier(user: dict[str, Any]) -> str:
    direct_user_id = _normalize_optional_identifier(user.get("id"))
    if direct_user_id is not None:
        return direct_user_id

    profile = user.get("public_user_profile")
    if isinstance(profile, dict):
        nested_user_id = _normalize_optional_identifier(profile.get("user_id"))
        if nested_user_id is not None:
            return nested_user_id

    raise InboxNormalizationError(
        "user_id_missing",
        "Chat user payload does not contain a user identifier.",
    )


def _extract_avatar_url(profile: dict[str, Any]) -> str | None:
    avatar = profile.get("avatar")
    if not isinstance(avatar, dict):
        return None

    default_avatar = _normalize_optional_text(avatar.get("default"))
    if default_avatar is not None:
        return default_avatar

    images = avatar.get("images")
    if not isinstance(images, dict):
        return None

    preferred_sizes = (
        "256x256",
        "192x192",
        "128x128",
        "96x96",
        "72x72",
        "64x64",
        "48x48",
        "36x36",
        "24x24",
    )
    for size in preferred_sizes:
        normalized = _normalize_optional_text(images.get(size))
        if normalized is not None:
            return normalized

    for value in images.values():
        normalized = _normalize_optional_text(value)
        if normalized is not None:
            return normalized

    return None


def _extract_listing_image_url(value: dict[str, Any]) -> str | None:
    images = value.get("images")
    if not isinstance(images, dict):
        return None
    main = images.get("main")
    if not isinstance(main, dict):
        return None

    preferred_sizes = ("140x105",)
    for size in preferred_sizes:
        normalized = _normalize_optional_text(main.get(size))
        if normalized is not None:
            return normalized

    for image_url in main.values():
        normalized = _normalize_optional_text(image_url)
        if normalized is not None:
            return normalized

    return None


def _expect_object(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InboxNormalizationError(
            "payload_invalid",
            f"{field} must be an object.",
        )
    return dict(value)


def _normalize_optional_identifier(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized


def _normalize_required_identifier(value: Any, *, field: str) -> str:
    normalized = _normalize_optional_identifier(value)
    if normalized is None:
        raise InboxNormalizationError(
            "identifier_missing",
            f"{field} is required.",
        )
    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized


def _normalize_required_text(value: Any, *, field: str) -> str:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        raise InboxNormalizationError(
            "text_missing",
            f"{field} is required.",
        )
    return normalized


def _normalize_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise InboxNormalizationError(
        "bool_invalid",
        "Boolean field must be true, false or null.",
    )


def _timestamp_to_datetime(value: Any, *, field: str) -> datetime:
    if value is None:
        raise InboxNormalizationError(
            "timestamp_missing",
            f"{field} is required.",
        )
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise InboxNormalizationError(
            "timestamp_invalid",
            f"{field} must be a valid Unix timestamp.",
        ) from exc


def _timestamp_to_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise InboxNormalizationError(
            "timestamp_invalid",
            "Optional timestamp field must be a valid Unix timestamp.",
        ) from exc
