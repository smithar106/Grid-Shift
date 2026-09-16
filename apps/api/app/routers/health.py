"""Health and readiness endpoints used by Railway and the frontend."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
    }


@router.get("/ready")
def ready(response: Response) -> dict[str, Any]:
    """Readiness probe. Reports database configuration without requiring it yet."""
    settings = get_settings()
    configured = bool(settings.database_url)
    if not configured:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if configured else "degraded", "database_configured": configured}
