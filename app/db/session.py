"""SQLAlchemy engine and session factory helpers."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings, get_settings


def make_engine(settings: Settings | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured PostgreSQL database."""
    current_settings = settings or get_settings()
    return create_engine(
        current_settings.database_url,
        echo=current_settings.db_echo,
        pool_pre_ping=current_settings.db_pool_pre_ping,
    )


@lru_cache
def get_engine() -> Engine:
    """Return the shared process engine."""
    return make_engine()


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the shared SQLAlchemy session factory."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_session() -> Iterator[Session]:
    """Yield a database session for request or command use."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_database_connection(engine: Engine | None = None) -> None:
    """Execute a lightweight probe against the configured database."""
    active_engine = engine or get_engine()
    with active_engine.connect() as connection:
        connection.execute(text("SELECT 1"))
