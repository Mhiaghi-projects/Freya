"""Fábrica de aplicaciones FastAPI de Freya.

Un servicio se monta con `create_app(...)` y hereda logging, middleware de
contexto, manejadores de error y endpoints operativos ya conformes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from .config import BaseServiceSettings
from .envelope import EnvelopeMiddleware
from .errors import install_error_handlers
from .health import ReadinessCheck, build_router
from .logging import configure_logging
from .middleware import ContextMiddleware


def create_app(
    settings: BaseServiceSettings,
    *,
    title: str | None = None,
    lifespan: Callable[..., Any] | None = None,
    readiness_checks: dict[str, ReadinessCheck] | None = None,
) -> FastAPI:
    configure_logging(settings.service_name, settings.log_level)

    app = FastAPI(
        title=title or settings.service_name,
        version=settings.service_version,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Orden de ejecución en request: Envelope (fuera) -> Context (dentro) ->
    # ruta. En response va al revés, así que Envelope ve el body ya
    # generado con el contexto (tenant, request_id) que Context dejó fijado.
    app.add_middleware(ContextMiddleware, default_tenant=settings.default_tenant)
    app.add_middleware(EnvelopeMiddleware)
    install_error_handlers(app, settings.service_name)
    app.include_router(
        build_router(
            settings.service_name, settings.service_version, readiness_checks
        )
    )
    return app
