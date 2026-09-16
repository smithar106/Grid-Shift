"""FastAPI application factory for GridShift."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.connectors.base import UpstreamUnavailable
from app.optimization.problem import ProblemValidationError
from app.routers import datasets, facilities, health, scenarios, weather
from app.schemas.ingestion import DatasetValidationError
from app.services.scenario_builder import ScenarioBuildError

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "Energy data ingestion and workload optimization for data centers. "
            "Every recommendation is traceable to an archived input snapshot."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(facilities.router, prefix=API_PREFIX)
    app.include_router(datasets.router, prefix=API_PREFIX)
    app.include_router(scenarios.router, prefix=API_PREFIX)
    app.include_router(weather.router, prefix=API_PREFIX)

    _register_domain_error_handlers(app)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": settings.app_name, "docs": "/docs", "health": f"{API_PREFIX}/health"}

    return app


def _register_domain_error_handlers(app: FastAPI) -> None:
    """Translate domain errors into actionable HTTP responses.

    Each handler surfaces the specific reasons rather than a generic message, because the
    difference between "your CSV has a duplicate hour" and "bad request" is the difference
    between a fixable file and a support ticket.
    """

    @app.exception_handler(DatasetValidationError)
    async def _dataset_error(_: Request, exc: DatasetValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "invalid_dataset",
                "message": str(exc),
                "issues": [str(issue) for issue in exc.issues],
            },
        )

    @app.exception_handler(ProblemValidationError)
    async def _problem_error(_: Request, exc: ProblemValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "invalid_problem",
                "message": str(exc),
                "reasons": list(exc.reasons),
            },
        )

    @app.exception_handler(ScenarioBuildError)
    async def _scenario_error(_: Request, exc: ScenarioBuildError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "invalid_scenario",
                "message": str(exc),
                "reasons": list(exc.reasons),
            },
        )

    @app.exception_handler(UpstreamUnavailable)
    async def _upstream_error(_: Request, exc: UpstreamUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "upstream_unavailable", "message": str(exc)},
        )


app = create_app()
