"""System endpoints for platform checks."""

from fastapi import APIRouter

from app.core.settings import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    """Return a lightweight health response."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@router.get("/version")
def version() -> dict[str, str]:
    """Return application version metadata."""
    settings = get_settings()
    return {
        "service": settings.app_name,
        "environment": settings.environment,
        "version": settings.version,
    }
