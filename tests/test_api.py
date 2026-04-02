from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.routes import inbox as inbox_routes
from app.inbox import (
    AvitoChatRead,
    AvitoClientRead,
    AvitoListingRead,
    AvitoMessageRead,
    ChatDetailsRead,
    DashboardSummaryRead,
    SyncAccountSummary,
)
from app.jobs.runner import JobRunResult
from app.main import app


class FakeInboxService:
    def __init__(self) -> None:
        self.chat_filters: list[dict[str, object]] = []
        self.message_filters: list[dict[str, object]] = []
        self.chat_detail_calls: list[dict[str, object]] = []

    def list_chats(self, **kwargs):
        self.chat_filters.append(kwargs)
        return (
            AvitoChatRead(
                id=1,
                account_id=kwargs.get("account_id") or 101,
                external_chat_id="chat-1",
                chat_type=kwargs.get("chat_type") or "u2i",
                client_id=11,
                listing_id=21,
                external_created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                external_updated_at=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
                last_message_at=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
                last_message_id="message-2",
                last_message_direction="out",
                last_message_type="text",
                message_count=2,
                created_at=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
            ),
        )

    def get_chat_details(self, **kwargs):
        self.chat_detail_calls.append(kwargs)
        if kwargs["chat_id"] == 404:
            return None
        messages: tuple[AvitoMessageRead, ...] = ()
        if kwargs["message_limit"] != 0:
            messages = (
                AvitoMessageRead(
                    id=1,
                    account_id=kwargs.get("account_id") or 101,
                    chat_id=kwargs["chat_id"],
                    external_message_id="message-1",
                    author_external_id="2002",
                    direction="in",
                    message_type="text",
                    text="Hello",
                    content_json={"text": "Hello"},
                    quote_json=None,
                    is_read=True,
                    read_at=datetime(2026, 4, 2, 10, 1, tzinfo=UTC),
                    external_created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                    created_at=datetime(2026, 4, 2, 10, 0, 1, tzinfo=UTC),
                ),
            )
        return ChatDetailsRead(
            chat=self.list_chats(account_id=kwargs.get("account_id"))[0],
            client=AvitoClientRead(
                id=11,
                account_id=kwargs.get("account_id") or 101,
                external_user_id="2002",
                display_name="Buyer",
                profile_url="https://avito.ru/user/buyer/profile",
                avatar_url=None,
                created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
            ),
            listing=AvitoListingRead(
                id=21,
                account_id=kwargs.get("account_id") or 101,
                external_item_id="1768287444",
                title="Mazda 3 2008",
                url="https://avito.ru/item/1768287444",
                price_string="300 000 RUB",
                status_id="10",
                owner_external_user_id="1001",
                image_url=None,
                created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
            ),
            messages=messages,
        )

    def list_messages(self, **kwargs):
        self.message_filters.append(kwargs)
        return (
            AvitoMessageRead(
                id=1,
                account_id=kwargs.get("account_id") or 101,
                chat_id=kwargs.get("chat_id") or 1,
                external_message_id="message-1",
                author_external_id="2002",
                direction=kwargs.get("direction") or "in",
                message_type=kwargs.get("message_type") or "text",
                text="Hello",
                content_json={"text": "Hello"},
                quote_json=None,
                is_read=True,
                read_at=datetime(2026, 4, 2, 10, 1, tzinfo=UTC),
                external_created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                created_at=datetime(2026, 4, 2, 10, 0, 1, tzinfo=UTC),
            ),
        )

    def list_clients(self, **kwargs):
        return (
            AvitoClientRead(
                id=11,
                account_id=kwargs.get("account_id") or 101,
                external_user_id="2002",
                display_name="Buyer",
                profile_url="https://avito.ru/user/buyer/profile",
                avatar_url=None,
                created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
            ),
        )

    def list_listings(self, **kwargs):
        return (
            AvitoListingRead(
                id=21,
                account_id=kwargs.get("account_id") or 101,
                external_item_id="1768287444",
                title="Mazda 3 2008",
                url="https://avito.ru/item/1768287444",
                price_string="300 000 RUB",
                status_id="10",
                owner_external_user_id="1001",
                image_url=None,
                created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
            ),
        )

    def get_dashboard_summary(self):
        return DashboardSummaryRead(
            total_accounts=1,
            active_accounts=1,
            total_chats=1,
            total_messages=2,
            total_clients=1,
            total_listings=1,
            accounts=(
                SyncAccountSummary(
                    account_id=101,
                    account_name="Store A",
                    avito_user_id="1001",
                    is_active=True,
                    last_inbox_sync_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
                    last_inbox_sync_status="success",
                    last_inbox_error=None,
                    chat_count=1,
                    message_count=2,
                ),
            ),
        )


@pytest.fixture()
def client() -> TestClient:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_version_endpoint(client: TestClient) -> None:
    response = client.get("/version")

    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"


def test_inbox_chats_endpoint_applies_filters(client: TestClient) -> None:
    service = FakeInboxService()
    app.dependency_overrides[inbox_routes.get_inbox_service] = lambda: service

    response = client.get(
        "/inbox/chats",
        params={
            "account_id": 101,
            "chat_type": "u2i",
            "has_listing": "true",
            "limit": 25,
            "offset": 5,
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["external_chat_id"] == "chat-1"
    assert service.chat_filters[0] == {
        "account_id": 101,
        "chat_type": "u2i",
        "has_listing": True,
        "limit": 25,
        "offset": 5,
    }


def test_inbox_chat_detail_endpoint_returns_header_by_default(client: TestClient) -> None:
    service = FakeInboxService()
    app.dependency_overrides[inbox_routes.get_inbox_service] = lambda: service

    response = client.get("/inbox/chats/1", params={"account_id": 101})

    assert response.status_code == 200
    assert response.json()["chat"]["external_chat_id"] == "chat-1"
    assert response.json()["messages"] == []
    assert service.chat_detail_calls[0]["message_limit"] == 0


def test_inbox_messages_endpoint_applies_filters(client: TestClient) -> None:
    service = FakeInboxService()
    app.dependency_overrides[inbox_routes.get_inbox_service] = lambda: service

    response = client.get(
        "/inbox/messages",
        params={
            "account_id": 101,
            "chat_id": 1,
            "direction": "out",
            "message_type": "image",
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["direction"] == "out"
    assert service.message_filters[0]["message_type"] == "image"


def test_inbox_dashboard_summary_endpoint(client: TestClient) -> None:
    app.dependency_overrides[inbox_routes.get_inbox_service] = FakeInboxService

    response = client.get("/inbox/dashboard/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_chats"] == 1
    assert payload["accounts"][0]["account_name"] == "Store A"


def test_inbox_sync_endpoint_runs_registered_job(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        inbox_routes,
        "run_registered_job",
        lambda **kwargs: JobRunResult(
            run_id=17,
            module_id=2,
            module_name="module2_inbox",
            job_name="inbox-sync",
            trigger_source=kwargs["trigger_source"],
            account_id=kwargs["account_id"],
            status="success",
            error_message=None,
            payload={"status": "success", "messages_synced": 2},
        ),
    )

    response = client.post("/inbox/sync/accounts/101")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_name"] == "inbox-sync"
    assert payload["payload"]["messages_synced"] == 2
