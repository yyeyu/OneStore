from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.admin import routes as admin_routes
from app.inbox import (
    AvitoChatRead,
    AvitoClientRead,
    AvitoListingRead,
    AvitoMessageRead,
    ChatDetailsRead,
    DashboardSummaryRead,
    SyncAccountSummary,
)
from app.main import app
from app.modules import AccountSummary, ModuleSettingSummary, ModuleSummary


class FakeInboxService:
    def list_chats(self, **kwargs):
        return (
            AvitoChatRead(
                id=1,
                account_id=kwargs.get("account_id") or 101,
                external_chat_id="chat-1",
                chat_type="u2i",
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
        if kwargs["chat_id"] == 404:
            return None
        return ChatDetailsRead(
            chat=self.list_chats(account_id=kwargs.get("account_id"))[0],
            client=AvitoClientRead(
                id=11,
                account_id=kwargs.get("account_id") or 101,
                external_user_id="2002",
                display_name="Buyer",
                profile_url="https://avito.ru/user/buyer/profile",
                avatar_url="https://example.test/avatar.png",
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
                image_url="https://example.test/item.jpg",
                created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
            ),
            messages=(
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
            ),
        )

    def list_messages(self, **kwargs):
        return self.get_chat_details(chat_id=kwargs.get("chat_id") or 1).messages

    def list_clients(self, **kwargs):
        return (
            AvitoClientRead(
                id=11,
                account_id=kwargs.get("account_id") or 101,
                external_user_id="2002",
                display_name="Buyer",
                profile_url="https://avito.ru/user/buyer/profile",
                avatar_url="https://example.test/avatar.png",
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
                image_url="https://example.test/item.jpg",
                created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
            ),
        )

    def get_dashboard_summary(self):
        return DashboardSummaryRead(
            total_accounts=2,
            active_accounts=1,
            total_chats=1,
            total_messages=1,
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
                    message_count=1,
                ),
                SyncAccountSummary(
                    account_id=102,
                    account_name="Store B",
                    avito_user_id=None,
                    is_active=False,
                    last_inbox_sync_at=None,
                    last_inbox_sync_status="error",
                    last_inbox_error="token missing",
                    chat_count=0,
                    message_count=0,
                ),
            ),
        )


class FakeOperationsService:
    def list_accounts(self):
        return (
            AccountSummary(
                id=101,
                name="Store A",
                client_id="store-a",
                avito_user_id="1001",
                is_active=True,
                last_inbox_sync_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
                last_inbox_sync_status="success",
                last_inbox_error=None,
                created_at=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
            ),
            AccountSummary(
                id=102,
                name="Store B",
                client_id="store-b",
                avito_user_id=None,
                is_active=False,
                last_inbox_sync_at=None,
                last_inbox_sync_status="error",
                last_inbox_error="token missing",
                created_at=datetime(2026, 4, 2, 9, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
            ),
        )

    def list_module_settings(self, **kwargs):
        return (
            ModuleSettingSummary(
                account_id=101,
                module_id=2,
                module_name=kwargs.get("module_name") or "module2_inbox",
                is_enabled=True,
                created_at=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
            ),
            ModuleSettingSummary(
                account_id=102,
                module_id=2,
                module_name=kwargs.get("module_name") or "module2_inbox",
                is_enabled=False,
                created_at=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
                updated_at=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
            ),
        )

    def list_modules(self):
        return (
            ModuleSummary(id=1, name="system_core"),
            ModuleSummary(id=2, name="module2_inbox"),
        )


@pytest.fixture()
def client() -> TestClient:
    app.dependency_overrides.clear()
    app.dependency_overrides[admin_routes.get_inbox_service] = FakeInboxService
    app.dependency_overrides[admin_routes.get_module_operations_service] = (
        FakeOperationsService
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_admin_dashboard_page_renders_summary(client: TestClient) -> None:
    response = client.get("/admin/")

    assert response.status_code == 200
    assert "Per-account inbox state" in response.text
    assert "Store A" in response.text
    assert "1 with module2_inbox" in response.text


def test_admin_accounts_page_renders_sync_buttons(client: TestClient) -> None:
    response = client.get("/admin/accounts")

    assert response.status_code == 200
    assert 'data-sync-url="/inbox/sync/accounts/101"' in response.text
    assert "module2_inbox" in response.text
    assert "token missing" in response.text


def test_admin_chats_and_details_pages_render(client: TestClient) -> None:
    chats_response = client.get("/admin/inbox/chats", params={"account_id": 101})
    details_response = client.get("/admin/inbox/chats/1", params={"account_id": 101})

    assert chats_response.status_code == 200
    assert "chat-1" in chats_response.text
    assert details_response.status_code == 200
    assert "Mazda 3 2008" in details_response.text
    assert "Hello" in details_response.text


def test_admin_system_page_renders_job_registry(client: TestClient) -> None:
    response = client.get("/admin/system")

    assert response.status_code == 200
    assert "Job Registry" in response.text
    assert "inbox-sync" in response.text


def test_admin_clients_and_listings_pages_render(client: TestClient) -> None:
    clients_response = client.get("/admin/inbox/clients", params={"account_id": 101})
    listings_response = client.get("/admin/inbox/listings", params={"account_id": 101})

    assert clients_response.status_code == 200
    assert "Buyer" in clients_response.text
    assert "profile" in clients_response.text

    assert listings_response.status_code == 200
    assert "Mazda 3 2008" in listings_response.text
    assert "300 000 RUB" in listings_response.text
