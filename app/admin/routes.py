"""Server-rendered admin routes mounted inside the main FastAPI app."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.admin.views import (
    build_accounts_view,
    build_chat_details_view,
    build_chats_view,
    build_clients_view,
    build_dashboard_view,
    build_listings_view,
    build_messages_view,
    build_system_view,
)
from app.inbox import InboxService
from app.modules import ModuleOperationsService

router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def get_inbox_service() -> InboxService:
    """Build the inbox service for admin page requests."""
    return InboxService()


def get_module_operations_service() -> ModuleOperationsService:
    """Build the operations service for admin page requests."""
    return ModuleOperationsService()


def format_datetime(value: datetime | None) -> str:
    """Render datetimes consistently inside templates."""
    if value is None:
        return "-"
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


templates.env.filters["datetime"] = format_datetime


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    inbox_service: InboxService = Depends(get_inbox_service),
    operations_service: ModuleOperationsService = Depends(get_module_operations_service),
) -> HTMLResponse:
    """Render the admin dashboard."""
    page = build_dashboard_view(
        inbox_service=inbox_service,
        operations_service=operations_service,
    )
    return _render(
        request,
        template_name="dashboard.html",
        section="dashboard",
        title="Dashboard",
        page=page,
    )


@router.get("/accounts", response_class=HTMLResponse)
def accounts(
    request: Request,
    operations_service: ModuleOperationsService = Depends(get_module_operations_service),
) -> HTMLResponse:
    """Render the accounts page."""
    page = build_accounts_view(operations_service=operations_service)
    return _render(
        request,
        template_name="accounts.html",
        section="accounts",
        title="Accounts",
        page=page,
    )


@router.get("/inbox/chats", response_class=HTMLResponse)
def chats(
    request: Request,
    account_id: int | None = Query(default=None),
    chat_type: str | None = Query(default=None),
    has_listing: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    inbox_service: InboxService = Depends(get_inbox_service),
    operations_service: ModuleOperationsService = Depends(get_module_operations_service),
) -> HTMLResponse:
    """Render the chats page."""
    page = build_chats_view(
        inbox_service=inbox_service,
        operations_service=operations_service,
        account_id=account_id,
        chat_type=chat_type,
        has_listing=has_listing,
        limit=limit,
        offset=offset,
    )
    return _render(
        request,
        template_name="inbox_chats.html",
        section="chats",
        title="Chats",
        page=page,
    )


@router.get("/inbox/chats/{chat_id}", response_class=HTMLResponse)
def chat_details(
    request: Request,
    chat_id: int,
    account_id: int | None = Query(default=None),
    inbox_service: InboxService = Depends(get_inbox_service),
    operations_service: ModuleOperationsService = Depends(get_module_operations_service),
) -> HTMLResponse:
    """Render one chat details page."""
    page = build_chat_details_view(
        inbox_service=inbox_service,
        operations_service=operations_service,
        chat_id=chat_id,
        account_id=account_id,
    )
    if page is None:
        raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' was not found.")
    return _render(
        request,
        template_name="inbox_chat_details.html",
        section="chats",
        title=f"Chat {chat_id}",
        page=page,
    )


@router.get("/inbox/messages", response_class=HTMLResponse)
def messages(
    request: Request,
    account_id: int | None = Query(default=None),
    chat_id: int | None = Query(default=None),
    direction: str | None = Query(default=None),
    message_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    inbox_service: InboxService = Depends(get_inbox_service),
    operations_service: ModuleOperationsService = Depends(get_module_operations_service),
) -> HTMLResponse:
    """Render the messages page."""
    page = build_messages_view(
        inbox_service=inbox_service,
        operations_service=operations_service,
        account_id=account_id,
        chat_id=chat_id,
        direction=direction,
        message_type=message_type,
        limit=limit,
        offset=offset,
    )
    return _render(
        request,
        template_name="inbox_messages.html",
        section="messages",
        title="Messages",
        page=page,
    )


@router.get("/inbox/clients", response_class=HTMLResponse)
def clients(
    request: Request,
    account_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    inbox_service: InboxService = Depends(get_inbox_service),
    operations_service: ModuleOperationsService = Depends(get_module_operations_service),
) -> HTMLResponse:
    """Render the clients page."""
    page = build_clients_view(
        inbox_service=inbox_service,
        operations_service=operations_service,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )
    return _render(
        request,
        template_name="inbox_clients.html",
        section="clients",
        title="Clients",
        page=page,
    )


@router.get("/inbox/listings", response_class=HTMLResponse)
def listings(
    request: Request,
    account_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    inbox_service: InboxService = Depends(get_inbox_service),
    operations_service: ModuleOperationsService = Depends(get_module_operations_service),
) -> HTMLResponse:
    """Render the listings page."""
    page = build_listings_view(
        inbox_service=inbox_service,
        operations_service=operations_service,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )
    return _render(
        request,
        template_name="inbox_listings.html",
        section="listings",
        title="Listings",
        page=page,
    )


@router.get("/system", response_class=HTMLResponse)
def system(
    request: Request,
    operations_service: ModuleOperationsService = Depends(get_module_operations_service),
) -> HTMLResponse:
    """Render the system page."""
    page = build_system_view(operations_service=operations_service)
    return _render(
        request,
        template_name="system.html",
        section="system",
        title="System",
        page=page,
    )


def _render(
    request: Request,
    *,
    template_name: str,
    section: str,
    title: str,
    page: object,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            "request": request,
            "section": section,
            "title": title,
            "page": page,
        },
    )
