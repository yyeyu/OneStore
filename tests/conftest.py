from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

import pytest

from app.db import check_database_connection, upgrade_database


@lru_cache
def is_postgresql_available() -> bool:
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
