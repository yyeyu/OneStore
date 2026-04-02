"""Read-only API endpoints for the Module 2 inbox slice."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.inbox import (
    AvitoChatRead,
    AvitoClientRead,
    AvitoListingRead,
    AvitoMessageRead,
    ChatDetailsRead,
    DashboardSummaryRead,
    InboxRepositoryError,
    InboxService,
)
from app.jobs import JobRunResult, run_registered_job
from app.modules import ModuleRunAccessError

router = APIRouter(prefix="/inbox", tags=["inbox"])


def get_inbox_service() -> InboxService:
    """Build the inbox service for API requests."""
    return InboxService()


@router.get("/chats", response_model=list[AvitoChatRead])
def list_chats(
    account_id: int | None = Query(default=None),
    chat_type: str | None = Query(default=None),
    has_listing: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    service: InboxService = Depends(get_inbox_service),
) -> list[AvitoChatRead]:
    """Return normalized inbox chats with lightweight list filters."""
    return list(
        service.list_chats(
            account_id=account_id,
            chat_type=chat_type,
            has_listing=has_listing,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/chats/{chat_id}", response_model=ChatDetailsRead)
def get_chat(
    chat_id: int,
    account_id: int | None = Query(default=None),
    include_messages: bool = Query(default=False),
    message_limit: int = Query(default=100, ge=0, le=500),
    service: InboxService = Depends(get_inbox_service),
) -> ChatDetailsRead:
    """Return one chat header plus related entities, optionally with messages."""
    details = service.get_chat_details(
        chat_id=chat_id,
        account_id=account_id,
        message_limit=(message_limit if include_messages else 0),
    )
    if details is None:
        raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' was not found.")
    return details


@router.get("/chats/{chat_id}/messages", response_model=list[AvitoMessageRead])
def list_chat_messages(
    chat_id: int,
    account_id: int | None = Query(default=None),
    direction: str | None = Query(default=None),
    message_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    service: InboxService = Depends(get_inbox_service),
) -> list[AvitoMessageRead]:
    """Return messages for one chat in stable chronological order."""
    return list(
        service.list_messages(
            account_id=account_id,
            chat_id=chat_id,
            direction=direction,
            message_type=message_type,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/messages", response_model=list[AvitoMessageRead])
def list_messages(
    account_id: int | None = Query(default=None),
    chat_id: int | None = Query(default=None),
    direction: str | None = Query(default=None),
    message_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    service: InboxService = Depends(get_inbox_service),
) -> list[AvitoMessageRead]:
    """Return normalized inbox messages with optional account/chat filters."""
    return list(
        service.list_messages(
            account_id=account_id,
            chat_id=chat_id,
            direction=direction,
            message_type=message_type,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/clients", response_model=list[AvitoClientRead])
def list_clients(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    service: InboxService = Depends(get_inbox_service),
) -> list[AvitoClientRead]:
    """Return normalized inbox clients."""
    return list(
        service.list_clients(
            account_id=account_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/listings", response_model=list[AvitoListingRead])
def list_listings(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    service: InboxService = Depends(get_inbox_service),
) -> list[AvitoListingRead]:
    """Return lightweight listing references extracted from inbox traffic."""
    return list(
        service.list_listings(
            account_id=account_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/dashboard/summary", response_model=DashboardSummaryRead)
def get_dashboard_summary(
    service: InboxService = Depends(get_inbox_service),
) -> DashboardSummaryRead:
    """Return compact inbox dashboard counters and per-account sync status."""
    return service.get_dashboard_summary()


@router.post("/sync/accounts/{account_id}", response_model=JobRunResult)
def sync_account_inbox(account_id: int) -> JobRunResult:
    """Run one manual inbox sync through the shared job runtime."""
    try:
        return run_registered_job(
            job_name="inbox-sync",
            trigger_source="manual",
            account_id=account_id,
        )
    except ModuleRunAccessError as exc:
        status_code = 404 if exc.code == "account_not_found" else 409
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except InboxRepositoryError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
