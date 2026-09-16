"""Runtime configuration for the GridShift API.

All settings are supplied through environment variables so that the same image can run
locally, in CI, and on Railway without modification.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: object) -> object:
    """Accept either a JSON list or a comma-separated string for list settings."""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            return value
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return value


CsvList = Annotated[list[str], BeforeValidator(_split_csv)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "GridShift API"
    version: str = "0.1.0"
    environment: str = Field(default="development")

    # Persistence. Railway injects DATABASE_URL for the attached Postgres service.
    database_url: str = "sqlite:///./gridshift.db"

    # Browser origins allowed to call the API directly. The Next.js server proxies
    # same-origin requests, so this only needs to cover direct/dev access.
    cors_origins: CsvList = Field(default_factory=lambda: ["http://localhost:3000"])

    # External data
    open_meteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    http_timeout_seconds: float = 10.0
    cache_ttl_seconds: int = 900

    # Optimization guardrails
    solver_time_limit_seconds: float = 5.0
    max_workloads: int = 200
    max_horizon_hours: int = 168
    max_concurrent_optimizations: int = 4

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
