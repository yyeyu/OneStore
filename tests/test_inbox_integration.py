from __future__ import annotations

import json
from uuid import uuid4

import app.cli.app as cli_app_module
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from typer.testing import CliRunner

from app.api.app import create_app
from app.db import AvitoAccount, AvitoChat, AvitoClient, AvitoListingRef, AvitoMessage, get_engine, get_session_factory
from app.inbox import InboxService
from app.jobs import run_registered_job
from app.modules import ModuleOperationsService


pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("require_postgresql"),
]

runner = CliRunner()


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
            ),
        },
    )


def _build_inbox_service() -> InboxService:
    return InboxService(
        access_token_provider=lambda _: "access-token",
        messenger_client_factory=lambda _: _build_fake_client(),
    )


def _bootstrap_inbox_account() -> int:
    operations_service = ModuleOperationsService()
    operations_service.ensure_default_modules(["system_core", "module2_inbox"])
    suffix = uuid4().hex[:8]
    bootstrap = operations_service.bootstrap_local(
        name="Inbox Integration Account",
        client_id=f"inbox-int-client-{suffix}",
        client_secret=f"inbox-int-secret-{suffix}",
        avito_user_id=f"inbox-int-avito-{suffix}",
        module_name="system_core",
    )
    operations_service.set_module_state(
        account_id=bootstrap.account.account.id,
        module_name="module2_inbox",
        is_enabled=True,
    )
    return bootstrap.account.account.id


def test_postgresql_migrations_expose_module2_inbox_tables() -> None:
    inspector = inspect(get_engine())
    tables = set(inspector.get_table_names())

    assert {
        "avito_accounts",
        "avito_chats",
        "avito_messages",
        "avito_clients",
        "avito_listings_ref",
        "module_runs",
        "modules",
    }.issubset(tables)


def test_fake_inbox_job_sync_runs_end_to_end_in_postgresql() -> None:
    account_id = _bootstrap_inbox_account()
    result = run_registered_job(
        job_name="inbox-sync",
        trigger_source="manual",
        account_id=account_id,
        service=_build_inbox_service(),
    )

    assert result.status == "success"
    assert result.payload is not None
    assert result.payload["messages_synced"] == 2

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(AvitoAccount, account_id)
        assert account is not None
        assert account.last_inbox_sync_status == "success"
        assert account.last_inbox_sync_at is not None
        assert account.last_inbox_error is None

        assert session.scalar(
            select(func.count()).select_from(AvitoChat).where(AvitoChat.account_id == account_id)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(AvitoMessage).where(AvitoMessage.account_id == account_id)
        ) == 2
        assert session.scalar(
            select(func.count()).select_from(AvitoClient).where(AvitoClient.account_id == account_id)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(AvitoListingRef).where(AvitoListingRef.account_id == account_id)
        ) == 1


def test_inbox_api_and_admin_pages_expose_synced_rows_in_postgresql() -> None:
    account_id = _bootstrap_inbox_account()
    _build_inbox_service().sync_account_inbox(account_id)

    with TestClient(create_app()) as client:
        chats_response = client.get("/inbox/chats", params={"account_id": account_id})
        messages_response = client.get("/inbox/messages", params={"account_id": account_id})
        clients_response = client.get("/inbox/clients", params={"account_id": account_id})
        listings_response = client.get("/inbox/listings", params={"account_id": account_id})
        dashboard_response = client.get("/inbox/dashboard/summary")

        assert chats_response.status_code == 200
        chats_payload = chats_response.json()
        assert chats_payload[0]["external_chat_id"] == "chat-1"

        chat_id = chats_payload[0]["id"]
        details_response = client.get(
            f"/inbox/chats/{chat_id}",
            params={"account_id": account_id, "include_messages": True},
        )
        assert details_response.status_code == 200
        assert len(details_response.json()["messages"]) == 2

        assert messages_response.status_code == 200
        assert len(messages_response.json()) == 2
        assert clients_response.status_code == 200
        assert clients_response.json()[0]["external_user_id"] == "2002"
        assert listings_response.status_code == 200
        assert listings_response.json()[0]["external_item_id"] == "1768287444"
        assert dashboard_response.status_code == 200
        assert dashboard_response.json()["total_chats"] >= 1

        admin_dashboard = client.get("/admin/")
        admin_accounts = client.get("/admin/accounts")
        admin_chats = client.get("/admin/inbox/chats", params={"account_id": account_id})
        admin_details = client.get(
            f"/admin/inbox/chats/{chat_id}",
            params={"account_id": account_id},
        )
        admin_messages = client.get(
            "/admin/inbox/messages",
            params={"account_id": account_id},
        )
        admin_clients = client.get(
            "/admin/inbox/clients",
            params={"account_id": account_id},
        )
        admin_listings = client.get(
            "/admin/inbox/listings",
            params={"account_id": account_id},
        )

        assert admin_dashboard.status_code == 200
        assert "Per-account inbox state" in admin_dashboard.text
        assert admin_accounts.status_code == 200
        assert "module2_inbox" in admin_accounts.text
        assert admin_chats.status_code == 200
        assert "chat-1" in admin_chats.text
        assert admin_details.status_code == 200
        assert "Mazda 3 2008" in admin_details.text
        assert "Hello" in admin_details.text
        assert admin_messages.status_code == 200
        assert "Messages" in admin_messages.text
        assert admin_clients.status_code == 200
        assert "Buyer" in admin_clients.text
        assert admin_listings.status_code == 200
        assert "Mazda 3 2008" in admin_listings.text


def test_cli_sync_and_read_commands_work_with_fake_inbox_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = _bootstrap_inbox_account()
    service = _build_inbox_service()
    monkeypatch.setattr(cli_app_module, "get_inbox_service", lambda: service)

    sync_result = runner.invoke(cli_app_module.cli, ["sync-inbox", "--account-id", str(account_id)])
    chats_result = runner.invoke(
        cli_app_module.cli,
        ["list-chats", "--account-id", str(account_id)],
    )
    messages_result = runner.invoke(
        cli_app_module.cli,
        ["list-messages", "--account-id", str(account_id)],
    )
    clients_result = runner.invoke(
        cli_app_module.cli,
        ["list-clients", "--account-id", str(account_id)],
    )
    listings_result = runner.invoke(
        cli_app_module.cli,
        ["list-listings", "--account-id", str(account_id)],
    )

    assert sync_result.exit_code == 0
    assert chats_result.exit_code == 0
    assert messages_result.exit_code == 0
    assert clients_result.exit_code == 0
    assert listings_result.exit_code == 0

    assert json.loads(sync_result.stdout)["item"]["messages_synced"] == 2
    assert json.loads(chats_result.stdout)["items"][0]["external_chat_id"] == "chat-1"
    assert json.loads(messages_result.stdout)["items"][0]["external_message_id"] == "message-1"
    assert json.loads(clients_result.stdout)["items"][0]["external_user_id"] == "2002"
    assert json.loads(listings_result.stdout)["items"][0]["external_item_id"] == "1768287444"
