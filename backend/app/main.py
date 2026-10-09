"""Entrypoint da API do OpsPilot."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger, set_correlation_id
from app.db.session import dispose_engine, get_engine

CORRELATION_HEADER = "X-Correlation-ID"

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Configura logging no start e fecha o pool no shutdown."""
    configure_logging(settings.log_level, settings.log_json)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "app_startup",
        environment=settings.environment,
        llm_provider=settings.llm_provider,
        database="postgresql" if settings.is_postgres else "sqlite",
    )
    yield
    await dispose_engine()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    """Monta a aplicação FastAPI."""
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title="OpsPilot API",
        version=__version__,
        summary="Hub de operações, dados e IA para pequenas empresas.",
        description=(
            "API do OpsPilot. **Projeto demonstrativo** com dados sintéticos.\n\n"
            "Autentique-se em `POST /api/v1/auth/login` e use o token Bearer nas demais rotas."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[CORRELATION_HEADER],
    )

    @app.middleware("http")
    async def correlation_and_logging(request: Request, call_next: Any) -> Response:
        """Propaga o correlation id e registra a requisição."""
        correlation_id = set_correlation_id(request.headers.get(CORRELATION_HEADER))
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers[CORRELATION_HEADER] = correlation_id
        if request.url.path not in {"/health", "/health/live"}:
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        return response

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["Infraestrutura"], summary="Healthcheck completo")
    async def health(response: Response) -> dict[str, Any]:
        """Verifica aplicação e conectividade com o banco."""
        database_ok = True
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:  # pragma: no cover - depende de infraestrutura
            database_ok = False
            logger.warning("health_database_unavailable")
        if not database_ok:
            response.status_code = 503
        return {
            "status": "ok" if database_ok else "degraded",
            "version": __version__,
            "environment": settings.environment,
            "database": "ok" if database_ok else "unavailable",
            "llm_provider": settings.llm_provider,
        }

    @app.get("/health/live", tags=["Infraestrutura"], summary="Liveness simples")
    async def live() -> dict[str, str]:
        """Responde sem tocar em dependências externas."""
        return {"status": "ok"}

    return app


app = create_app()
