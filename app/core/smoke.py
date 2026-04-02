"""Local smoke-check workflow for the platform core and module2_inbox."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.actions import execute_probe_action
from app.api.app import create_app
from app.core.diagnostics import build_system_summary
from app.db import (
    ActionLog,
    AvitoChat,
    AvitoClient,
    AvitoListingRef,
    AvitoMessage,
    ModuleRun,
    get_session_factory,
)
from app.db.migrations import upgrade_database
from app.db.session import check_database_connection
from app.inbox import InboxService
from app.jobs import run_registered_job, run_scheduler_loop
from app.modules import ModuleOperationsService

SMOKE_ACCOUNT_NAME = "Smoke Local Account"
SMOKE_CLIENT_ID = "smoke-local-client"
SMOKE_CLIENT_SECRET = "smoke-local-secret"
SMOKE_AVITO_USER_ID = "smoke-avito-user"
SMOKE_MODULE_NAMES = ("system_core", "module2_inbox")


class SmokeMessengerClient:
    """Deterministic fake Avito Messenger client used by smoke-check."""

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


def run_smoke_check() -> dict[str, object]:
    """Run a compact end-to-end smoke flow for system_core and module2_inbox."""
    system_summary = build_system_summary()
    upgrade_database()
    check_database_connection()

    scheduler_summary = run_scheduler_loop(interval_seconds=300, duration_seconds=0)

    operations_service = ModuleOperationsService()
    modules = operations_service.ensure_default_modules(SMOKE_MODULE_NAMES)
    module2_module = next(
        (module for module in modules if module.name == "module2_inbox"),
        None,
    )
    if module2_module is None:
        raise RuntimeError("module2_inbox is missing from the module catalog.")

    bootstrap_summary = operations_service.bootstrap_local(
        name=SMOKE_ACCOUNT_NAME,
        client_id=SMOKE_CLIENT_ID,
        client_secret=SMOKE_CLIENT_SECRET,
        avito_user_id=SMOKE_AVITO_USER_ID,
        module_name="system_core",
    )
    account_id = bootstrap_summary.account.account.id
    inbox_module_setting = operations_service.set_module_state(
        account_id=account_id,
        module_name="module2_inbox",
        is_enabled=True,
    )

    job_result = run_registered_job(
        job_name="account-system-probe",
        trigger_source="manual",
        account_id=account_id,
    )
    action_result = execute_probe_action(
        target="smoke-target",
        message=f"smoke:{uuid4().hex}",
        account_id=account_id,
        run_id=job_result.run_id,
    )
    inbox_job_result = run_registered_job(
        job_name="inbox-sync",
        trigger_source="manual",
        account_id=account_id,
        service=build_smoke_inbox_service(),
    )

    database_state = load_smoke_database_state(
        account_id=account_id,
        system_job_run_id=job_result.run_id,
        inbox_job_run_id=inbox_job_result.run_id,
        action_log_id=action_result.action_log_id,
    )

    with TestClient(create_app()) as client:
        health_response = client.get("/health")
        health_response.raise_for_status()
        http_surface = collect_smoke_http_surface(
            client,
            account_id=account_id,
            chat_id=database_state["chat_id"],
            external_chat_id=database_state["external_chat_id"],
            listing_title=database_state["listing_title"],
            client_name=database_state["client_name"],
        )

    return {
        "status": "ok",
        "system": system_summary,
        "api_health": health_response.json(),
        "scheduler": scheduler_summary,
        "bootstrap_account_id": account_id,
        "bootstrap_account_created": bootstrap_summary.account.created,
        "bootstrap_module_id": bootstrap_summary.module_setting.module_setting.module_id,
        "bootstrap_module_enabled": bootstrap_summary.module_setting.module_setting.is_enabled,
        "module2_inbox_present": True,
        "module2_inbox_module_id": module2_module.id,
        "module2_inbox_enabled": inbox_module_setting.module_setting.is_enabled,
        "job_status": job_result.status,
        "job_run_id": job_result.run_id,
        "job_recorded": database_state["job_recorded"],
        "job_finished_at_present": database_state["job_finished_at_present"],
        "action_status": action_result.status,
        "action_log_id": action_result.action_log_id,
        "action_recorded": database_state["action_recorded"],
        "action_has_run_link": database_state["action_has_run_link"],
        "inbox_job_status": inbox_job_result.status,
        "inbox_job_run_id": inbox_job_result.run_id,
        "inbox_job_recorded": database_state["inbox_job_recorded"],
        "inbox_job_finished_at_present": database_state["inbox_job_finished_at_present"],
        "inbox_payload": inbox_job_result.payload,
        "inbox_counts": {
            "chats": database_state["chat_count"],
            "messages": database_state["message_count"],
            "clients": database_state["client_count"],
            "listings": database_state["listing_count"],
        },
        "http_surface": http_surface,
    }


def build_smoke_inbox_service() -> InboxService:
    """Build the fake-sync inbox service used by smoke-check."""
    return InboxService(
        access_token_provider=lambda _: "smoke-access-token",
        messenger_client_factory=lambda _: build_smoke_messenger_client(),
    )


def build_smoke_messenger_client() -> SmokeMessengerClient:
    """Return the deterministic fake messenger client for smoke runs."""
    return SmokeMessengerClient(
        chats=(
            {
                "id": "smoke-chat-1",
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
                    {"id": 1001, "name": "Smoke Seller"},
                    {
                        "id": 2002,
                        "name": "Smoke Buyer",
                        "public_user_profile": {
                            "url": "https://avito.ru/user/buyer/profile",
                            "avatar": {
                                "default": "https://example.test/avatar.png",
                            },
                        },
                    },
                ],
                "last_message": {
                    "id": "smoke-message-2",
                    "created": 1712026800,
                    "direction": "out",
                    "type": "text",
                    "content": {"text": "Hi"},
                },
            },
        ),
        messages_by_chat_id={
            "smoke-chat-1": (
                {
                    "id": "smoke-message-1",
                    "author_id": 2002,
                    "direction": "in",
                    "type": "text",
                    "created": 1712023200,
                    "is_read": True,
                    "read": 1712023260,
                    "content": {"text": "Hello"},
                },
                {
                    "id": "smoke-message-2",
                    "author_id": 1001,
                    "direction": "out",
                    "type": "text",
                    "created": 1712026800,
                    "is_read": True,
                    "read": 1712026860,
                    "content": {"text": "Hi"},
                    "quote": {
                        "id": "smoke-message-1",
                        "author_id": 2002,
                        "created": 1712023200,
                        "type": "text",
                        "content": {"text": "Hello"},
                    },
                },
            ),
        },
    )


def load_smoke_database_state(
    *,
    account_id: int,
    system_job_run_id: int,
    inbox_job_run_id: int,
    action_log_id: int,
    session_factory: sessionmaker[Session] | Callable[[], Session] | None = None,
) -> dict[str, object]:
    """Read the critical persisted state created by smoke-check."""
    active_session_factory = session_factory or get_session_factory()
    with active_session_factory() as session:
        run_record = session.get(ModuleRun, system_job_run_id)
        inbox_run_record = session.get(ModuleRun, inbox_job_run_id)
        action_log = session.get(ActionLog, action_log_id)
        chat = session.execute(
            select(AvitoChat)
            .where(AvitoChat.account_id == account_id)
            .order_by(AvitoChat.id.desc())
        ).scalar_one_or_none()
        client = session.execute(
            select(AvitoClient)
            .where(AvitoClient.account_id == account_id)
            .order_by(AvitoClient.id.desc())
        ).scalar_one_or_none()
        listing = session.execute(
            select(AvitoListingRef)
            .where(AvitoListingRef.account_id == account_id)
            .order_by(AvitoListingRef.id.desc())
        ).scalar_one_or_none()

        return {
            "job_recorded": run_record is not None,
            "job_finished_at_present": bool(run_record and run_record.finished_at),
            "inbox_job_recorded": inbox_run_record is not None,
            "inbox_job_finished_at_present": bool(
                inbox_run_record and inbox_run_record.finished_at
            ),
            "action_recorded": action_log is not None,
            "action_has_run_link": bool(action_log and action_log.run_id == system_job_run_id),
            "chat_count": int(
                session.scalar(
                    select(func.count(AvitoChat.id)).where(AvitoChat.account_id == account_id)
                )
                or 0
            ),
            "message_count": int(
                session.scalar(
                    select(func.count(AvitoMessage.id)).where(
                        AvitoMessage.account_id == account_id
                    )
                )
                or 0
            ),
            "client_count": int(
                session.scalar(
                    select(func.count(AvitoClient.id)).where(
                        AvitoClient.account_id == account_id
                    )
                )
                or 0
            ),
            "listing_count": int(
                session.scalar(
                    select(func.count(AvitoListingRef.id)).where(
                        AvitoListingRef.account_id == account_id
                    )
                )
                or 0
            ),
            "chat_id": chat.id if chat is not None else None,
            "external_chat_id": chat.external_chat_id if chat is not None else None,
            "client_name": client.display_name if client is not None else None,
            "listing_title": listing.title if listing is not None else None,
        }


def collect_smoke_http_surface(
    client: TestClient,
    *,
    account_id: int,
    chat_id: int | None,
    external_chat_id: str | None,
    listing_title: str | None,
    client_name: str | None,
) -> dict[str, object]:
    """Validate API and admin availability for the smoke-seeded inbox data."""
    if chat_id is None:
        raise RuntimeError("Smoke inbox sync did not create a chat row.")

    chats_response = client.get("/inbox/chats", params={"account_id": account_id})
    chats_response.raise_for_status()
    messages_response = client.get("/inbox/messages", params={"account_id": account_id})
    messages_response.raise_for_status()
    clients_response = client.get("/inbox/clients", params={"account_id": account_id})
    clients_response.raise_for_status()
    listings_response = client.get("/inbox/listings", params={"account_id": account_id})
    listings_response.raise_for_status()
    chat_details_response = client.get(
        f"/inbox/chats/{chat_id}",
        params={"account_id": account_id, "include_messages": True},
    )
    chat_details_response.raise_for_status()
    dashboard_response = client.get("/inbox/dashboard/summary")
    dashboard_response.raise_for_status()

    admin_dashboard_response = client.get("/admin/")
    admin_dashboard_response.raise_for_status()
    admin_accounts_response = client.get("/admin/accounts")
    admin_accounts_response.raise_for_status()
    admin_chats_response = client.get(
        "/admin/inbox/chats",
        params={"account_id": account_id},
    )
    admin_chats_response.raise_for_status()
    admin_chat_details_response = client.get(
        f"/admin/inbox/chats/{chat_id}",
        params={"account_id": account_id},
    )
    admin_chat_details_response.raise_for_status()
    admin_messages_response = client.get(
        "/admin/inbox/messages",
        params={"account_id": account_id},
    )
    admin_messages_response.raise_for_status()
    admin_clients_response = client.get(
        "/admin/inbox/clients",
        params={"account_id": account_id},
    )
    admin_clients_response.raise_for_status()
    admin_listings_response = client.get(
        "/admin/inbox/listings",
        params={"account_id": account_id},
    )
    admin_listings_response.raise_for_status()

    chats_payload = chats_response.json()
    messages_payload = messages_response.json()
    clients_payload = clients_response.json()
    listings_payload = listings_response.json()
    details_payload = chat_details_response.json()
    dashboard_payload = dashboard_response.json()

    if not chats_payload or not messages_payload or not clients_payload or not listings_payload:
        raise RuntimeError("Smoke HTTP surface did not return seeded inbox rows.")

    surface = {
        "api": {
            "chat_count": len(chats_payload),
            "message_count": len(messages_payload),
            "client_count": len(clients_payload),
            "listing_count": len(listings_payload),
            "dashboard_total_chats": dashboard_payload["total_chats"],
            "dashboard_total_messages": dashboard_payload["total_messages"],
            "chat_details_message_count": len(details_payload["messages"]),
        },
        "admin": {
            "dashboard_ok": "Per-account inbox state" in admin_dashboard_response.text,
            "accounts_ok": "module2_inbox" in admin_accounts_response.text,
            "chats_ok": bool(external_chat_id and external_chat_id in admin_chats_response.text),
            "chat_details_ok": bool(
                (listing_title and listing_title in admin_chat_details_response.text)
                or (client_name and client_name in admin_chat_details_response.text)
            ),
            "messages_ok": "Messages" in admin_messages_response.text,
            "clients_ok": bool(client_name and client_name in admin_clients_response.text),
            "listings_ok": bool(
                listing_title and listing_title in admin_listings_response.text
            ),
        },
    }
    if surface["api"]["chat_details_message_count"] <= 0:
        raise RuntimeError("Smoke API chat details did not return message history.")
    if not all(bool(value) for value in surface["admin"].values()):
        raise RuntimeError("Smoke admin surface did not render the expected inbox data.")
    return surface
