"""Runtime configuration for the GridShift API.

All settings are supplied through environment variables so that the same image can run
locally, in CI, and on Railway without modification.

Note: list-like settings are declared as plain strings with parsed accessors. Pydantic
Settings attempts to JSON-decode complex (list/dict) annotations straight from the
environment before validators run, which would reject the comma-separated form that
Railway and .env files naturally provide.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "GridShift API"
    version: str = "0.1.0"
    environment: str = Field(default="development")

    # Persistence. Railway injects DATABASE_URL for the attached Postgres service.
    database_url: str = "sqlite:///./gridshift.db"

    # Comma-separated browser origins allowed to call the API directly. The Next.js
    # server proxies same-origin requests, so this only needs to cover direct/dev access.
    cors_origins: str = "http://localhost:3000"

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
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """Return a SQLAlchemy URL that selects the psycopg 3 driver.

        Railway (and most providers) inject `postgresql://...`, which SQLAlchemy maps to
        the psycopg2 driver by default. This project installs psycopg 3, so the scheme is
        rewritten rather than rewriting the provider-supplied value.
        """
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                return "postgresql+psycopg://" + self.database_url[len(prefix) :]
        return self.database_url

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
