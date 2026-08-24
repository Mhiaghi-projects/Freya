"""Punto de entrada de athenea: notas tipo Notion sobre la malla de Freya
-- auth para usuarios, gestor-db para páginas/bloques, storage sólo a
través del gateway de frontend (nunca directo, ver docker-compose.yml)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from freya_common import (
    JwksCache,
    MigrationRunner,
    ServiceClient,
    ServiceTokenProvider,
    TokenVerifier,
    build_http_client,
    create_app,
)

from app.api import pages
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

    app.state.gestor_db = ServiceClient(
        settings.gestor_db_url, settings.service_name, app.state.http, app.state.tokens
    )

    app.state.migrations = MigrationRunner(
        app.state.gestor_db,
        tenant=settings.default_tenant,
        migrations_dir=Path("/srv/migrations"),
    )
    app.state.migrations.start()

    logger.info("servicio arrancado", extra={"version": settings.service_version})
    try:
        yield
    finally:
        await app.state.migrations.stop()
        await app.state.http.aclose()
        logger.info("servicio detenido")


async def check_gestor_db() -> str | None:
    try:
        response = await app.state.http.get(
            f"{settings.gestor_db_url}/health", timeout=3.0
        )
        return (
            None
            if response.status_code == 200
            else f"gestor-db devolvió {response.status_code}"
        )
    except Exception as exc:
        return f"gestor-db inalcanzable: {exc}"


async def check_migrations() -> str | None:
    return await app.state.migrations.ping()


app = create_app(
    settings,
    title="Freya athenea",
    lifespan=lifespan,
    readiness_checks={"gestor_db": check_gestor_db, "migrations": check_migrations},
)

app.include_router(pages.router, prefix="/api/v1")
