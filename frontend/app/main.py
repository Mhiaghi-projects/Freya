"""Punto de entrada de frontend: única puerta HTTPS al exterior
(docs/ROADMAP.md Fase 9). Sirve el panel (app/static) y hace de gateway
hacia el resto de la malla, reenviando siempre el token de la sesión del
propio usuario -- nunca eleva privilegios."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from freya_common import (
    JwksCache,
    SlidingWindowLimiter,
    TokenVerifier,
    build_http_client,
    create_app,
)

from app.api import (
    admin,
    athenea,
    catalog,
    cicd,
    gamification,
    git,
    projects,
    session,
    storage,
)
from app.config import get_settings
from app.infra.rate_limit import TenantRateLimitMiddleware

logger = logging.getLogger(__name__)
settings = get_settings()

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    ca = str(settings.ca_bundle_file) if settings.ca_bundle_file.exists() else None
    app.state.http = build_http_client(ca)

    if settings.auth_enabled:
        app.state.verifier = TokenVerifier(
            JwksCache(settings.auth_url, app.state.http, settings.jwks_cache_seconds),
            issuer=settings.auth_url,
        )
    else:
        app.state.verifier = None
        logger.warning("auth deshabilitado: modo bootstrap")

    logger.info("servicio arrancado", extra={"version": settings.service_version})
    try:
        yield
    finally:
        await app.state.http.aclose()
        logger.info("servicio detenido")


async def check_auth() -> str | None:
    try:
        response = await app.state.http.get(f"{settings.auth_url}/health", timeout=3.0)
        if response.status_code == 200:
            return None
        return f"auth devolvió {response.status_code}"
    except Exception as exc:
        return f"auth inalcanzable: {exc}"


app = create_app(
    settings,
    title="Freya frontend",
    lifespan=lifespan,
    readiness_checks={"auth": check_auth},
    expose_docs=False,
)

app.add_middleware(
    TenantRateLimitMiddleware,
    limiter=SlidingWindowLimiter(
        max_attempts=settings.tenant_rate_limit_max_attempts,
        window_seconds=settings.tenant_rate_limit_window_seconds,
    ),
)

app.include_router(session.router)
app.include_router(admin.router)
app.include_router(catalog.router)
app.include_router(git.router)
app.include_router(storage.router)
app.include_router(cicd.router)
app.include_router(projects.router)
app.include_router(gamification.router)
app.include_router(athenea.router)

# El SPA (login + panel) vive bajo /app: HTML/CSS/JS servidos tal cual, sin
# el sobre JSON (EnvelopeMiddleware sólo envuelve application/json). "/"
# redirige ahí -- ver app/static/index.html para el enrutado cliente.
app.mount("/app", StaticFiles(directory=_STATIC_DIR, html=True), name="static")


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/app/")
