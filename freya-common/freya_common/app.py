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
from .security_headers import SecurityHeadersMiddleware


def create_app(
    settings: BaseServiceSettings,
    *,
    title: str | None = None,
    lifespan: Callable[..., Any] | None = None,
    readiness_checks: dict[str, ReadinessCheck] | None = None,
    expose_docs: bool = True,
) -> FastAPI:
    configure_logging(settings.service_name, settings.log_level)

    # expose_docs=False para el único servicio que de verdad es alcanzable
    # desde fuera (frontend, vía Traefik): /api/v1/docs y /openapi.json
    # publican el mapa completo de rutas internas (admin, storage, git,
    # cicd...) a cualquiera que llegue al puerto público, sin necesitar
    # ninguna credencial para VERLO -- no da acceso por sí solo (cada ruta
    # sigue exigiendo su propio JWT), pero es reconocimiento gratis que no
    # tiene sentido regalar. Los otros 9 servicios viven en freya-mesh, sin
    # puerto publicado -- ahí los docs sólo ayudan a depurar en local.
    app = FastAPI(
        title=title or settings.service_name,
        version=settings.service_version,
        docs_url="/api/v1/docs" if expose_docs else None,
        openapi_url="/api/v1/openapi.json" if expose_docs else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Orden de ejecución en request: SecurityHeaders (fuera) -> Envelope ->
    # Context (dentro) -> ruta. En response va al revés -- SecurityHeaders
    # tiene que ser la más externa para que sus cabeceras sobrevivan a la
    # respuesta ya reescrita por Envelope, en vez de arriesgarse a que
    # _rebuild_headers las descarte por no venir en la Response original.
    app.add_middleware(ContextMiddleware, default_tenant=settings.default_tenant)
    app.add_middleware(EnvelopeMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    install_error_handlers(app)
    app.include_router(
        build_router(
            settings.service_name, settings.service_version, readiness_checks
        )
    )
    return app
