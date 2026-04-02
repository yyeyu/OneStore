from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
import socket

import pytest
from sqlalchemy.engine import make_url

from app.core.settings import get_settings
from app.db import check_database_connection, upgrade_database


def _postgresql_host_is_reachable() -> bool:
    settings = get_settings()
    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        return True
    if url.host is None:
        return True

    try:
        with socket.create_connection((url.host, url.port or 5432), timeout=1.0):
            return True
    except OSError:
        return False


@lru_cache
def is_postgresql_available() -> bool:
    if not _postgresql_host_is_reachable():
        return False
    try:
        check_database_connection()
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def require_postgresql() -> Iterator[None]:
    if not is_postgresql_available():
        pytest.skip("Integration tests require a reachable PostgreSQL database.")

    upgrade_database()
    yield
