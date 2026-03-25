"""FastAPI application factory."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.routes.system import router as system_router
from app.core.logging import configure_logging
from app.core.settings import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(
        settings.log_level,
        settings.log_format,
        service=settings.app_name,
        environment=settings.environment,
    )
    logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "API startup",
            extra={
                "module_name": "system",
                "status": "started",
            },
        )
        yield
        logger.info(
            "API shutdown",
            extra={
                "module_name": "system",
                "status": "stopped",
            },
        )

    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.include_router(system_router)
    return application
