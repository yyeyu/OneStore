from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.inbox import (
    InboxNormalizationError,
    extract_client,
    extract_listing,
    normalize_chat,
    normalize_message,
)


def test_extract_client_prefers_counterparty_user() -> None:
    client = extract_client(
        [
            {
                "id": 1001,
                "name": "Seller",
                "public_user_profile": {
                    "url": "https://avito.ru/user/seller/profile",
                },
            },
            {
                "id": 2002,
                "name": "Buyer",
                "public_user_profile": {
                    "url": "https://avito.ru/user/buyer/profile",
                    "avatar": {
                        "default": "https://www.avito.st/avatar.png",
                    },
                },
            },
        ],
        account_user_id="1001",
    )

    assert client is not None
    assert client.external_user_id == "2002"
    assert client.display_name == "Buyer"
    assert client.profile_url == "https://avito.ru/user/buyer/profile"
    assert client.avatar_url == "https://www.avito.st/avatar.png"


def test_extract_listing_reads_context_value() -> None:
    listing = extract_listing(
        {
            "type": "item",
            "value": {
                "id": 1768287444,
                "title": "Mazda 3 2008",
                "url": "https://avito.ru/moskva/avtomobili/mazda_3_2008_1768287444",
                "price_string": "300 000 RUB",
                "status_id": 10,
                "user_id": 141906442,
                "images": {
                    "count": 4,
                    "main": {
                        "140x105": "https://01-img-staging-proxy.k.avito.ru/140x105/5815183159.jpg",
                    },
                },
            },
        }
    )

    assert listing is not None
    assert listing.external_item_id == "1768287444"
    assert listing.owner_external_user_id == "141906442"
    assert listing.image_url == "https://01-img-staging-proxy.k.avito.ru/140x105/5815183159.jpg"


def test_normalize_chat_extracts_summary_client_and_listing() -> None:
    normalized = normalize_chat(
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
                    },
                },
            ],
            "last_message": {
                "id": "message-2",
                "created": 1712026800,
                "direction": "in",
                "type": "text",
                "content": {"text": "Hello"},
            },
        },
        account_user_id="1001",
    )

    assert normalized.chat.external_chat_id == "chat-1"
    assert normalized.chat.chat_type == "u2i"
    assert normalized.chat.external_created_at == datetime(2024, 4, 2, 2, 0, tzinfo=UTC)
    assert normalized.chat.last_message_id == "message-2"
    assert normalized.client is not None
    assert normalized.client.external_user_id == "2002"
    assert normalized.listing is not None
    assert normalized.listing.external_item_id == "1768287444"


def test_normalize_message_preserves_content_and_quote() -> None:
    normalized = normalize_message(
        {
            "id": "message-1",
            "author_id": 2002,
            "direction": "in",
            "type": "link",
            "created": 1712023200,
            "is_read": True,
            "read": 1712023260,
            "content": {
                "link": {
                    "text": "habr.com",
                    "url": "https://habr.com/ru/",
                    "preview": {
                        "title": "Best articles",
                    },
                }
            },
            "quote": {
                "id": "message-0",
                "author_id": 1001,
                "created": 1712023100,
                "type": "text",
                "content": {
                    "text": "Original message",
                },
            },
        }
    )

    assert normalized.external_message_id == "message-1"
    assert normalized.author_external_id == "2002"
    assert normalized.text == "habr.com"
    assert normalized.content_json == {
        "link": {
            "text": "habr.com",
            "url": "https://habr.com/ru/",
            "preview": {
                "title": "Best articles",
            },
        }
    }
    assert normalized.quote_json == {
        "id": "message-0",
        "author_id": 1001,
        "created": 1712023100,
        "type": "text",
        "content": {
            "text": "Original message",
        },
    }
    assert normalized.read_at == datetime(2024, 4, 2, 2, 1, tzinfo=UTC)


def test_normalize_message_requires_content_object() -> None:
    with pytest.raises(InboxNormalizationError) as error:
        normalize_message(
            {
                "id": "message-1",
                "direction": "in",
                "type": "text",
                "created": 1712023200,
                "content": None,
            }
        )

    assert error.value.code == "payload_invalid"
