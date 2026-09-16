"""Database engine and session management.

The same code runs against SQLite locally and PostgreSQL in production. The URL comes
from ``DATABASE_URL`` (normalized in ``app.config``), so nothing here is environment
specific beyond a couple of connection-argument differences.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

__all__ = ["get_engine", "get_session", "get_session_factory", "reset_engine_cache"]


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    url = settings.sqlalchemy_url

    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        # SQLite connections are bound to the thread that created them, which conflicts
        # with FastAPI's threadpool for sync endpoints.
        connect_args["check_same_thread"] = False

    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args=connect_args,
        future=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine_cache() -> None:
    """Drop cached engine/session factory. Used by tests that swap DATABASE_URL."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
