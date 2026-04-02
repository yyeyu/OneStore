"""Runtime settings loaded from environment."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__


class Settings(BaseSettings):
    """Application settings for the current environment."""

    model_config = SettingsConfigDict(
        env_prefix="ONESTORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "OneStore"
    environment: str = "local"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    log_format: str = "text"
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/onestore"
    )
    db_echo: bool = False
    db_pool_pre_ping: bool = True
    version: str = __version__

    @property
    def project_root(self) -> Path:
        """Return the repository root for local tooling."""
        return Path(__file__).resolve().parents[2]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
