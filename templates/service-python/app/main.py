"""Punto de entrada de __SERVICE_NAME__."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from freya_common import (
    JwksCache,
    ServiceTokenProvider,
    TokenVerifier,
    build_http_client,
    create_app,
)

from app.api import example
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ca = str(settings.ca_bundle_file) if settings.ca_bundle_file.exists() else None
    app.state.http = build_http_client(ca)

    if settings.auth_enabled:
        app.state.tokens = ServiceTokenProvider(
            settings.auth_url,
            settings.service_name,
            settings.api_key,
            settings.api_secret,
            app.state.http,
        )
        app.state.verifier = TokenVerifier(
            JwksCache(settings.auth_url, app.state.http, settings.jwks_cache_seconds),
            issuer=settings.auth_url,
        )
    else:
        app.state.tokens = None
        app.state.verifier = None
        logger.warning("auth deshabilitado: modo bootstrap")

    logger.info("servicio arrancado", extra={"version": settings.service_version})
    try:
        yield
    finally:
        await app.state.http.aclose()
        logger.info("servicio detenido")


async def check_auth() -> str | None:
    """Comprobación de dependencia para /ready."""
    if not settings.auth_enabled:
        return None
    try:
        response = await app.state.http.get(f"{settings.auth_url}/health", timeout=3.0)
        return None if response.status_code == 200 else f"auth devolvió {response.status_code}"
    except Exception as exc:
        return f"auth inalcanzable: {exc}"


app = create_app(
    settings,
    title="Freya __SERVICE_NAME__",
    lifespan=lifespan,
    readiness_checks={"auth": check_auth},
)

app.include_router(example.router, prefix="/api/v1")
