"""Punto de entrada de gestor-db.

Única puerta a PostgreSQL de toda Freya (docs/ARCHITECTURE.md §3). El pool
de conexiones vive en app.state.db durante toda la vida del proceso; /ready
lo usa para reflejar el estado real de la base, no el de `auth` (gestor-db
no depende de auth hasta el retorno de la Fase 2, gdb-08).

Rutas sin prefijo /api/v1: es un contrato interno, no expuesto por el
gateway (docs/freya-api-contract.md §15).
"""

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

from app.api import admin, migrations, mutate, query, schemas, tables, transaction
from app.config import get_settings
from app.domain.pool import Database

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ca = str(settings.ca_bundle_file) if settings.ca_bundle_file.exists() else None
    app.state.http = build_http_client(ca)

    app.state.db = Database(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        command_timeout=settings.pool_command_timeout_seconds,
    )
    await app.state.db.start()

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
        await app.state.db.stop()
        await app.state.http.aclose()
        logger.info("servicio detenido")


async def check_database() -> str | None:
    """Comprobación de dependencia para /ready: el pool responde de verdad."""
    return await app.state.db.ping()


app = create_app(
    settings,
    title="Freya gestor-db",
    lifespan=lifespan,
    readiness_checks={"database": check_database},
)

app.include_router(query.router)
app.include_router(mutate.router)
app.include_router(transaction.router)
app.include_router(schemas.router)
app.include_router(tables.router)
app.include_router(migrations.router)
app.include_router(admin.router)
