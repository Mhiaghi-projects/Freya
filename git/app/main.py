"""Punto de entrada de git.

Envoltorio sobre `git http-backend` (docs/ARCHITECTURE.md §5): protocolo
smart HTTP real más una API de lectura/gestión (docs/freya-api-contract.md
§6). El contenedor no guarda estado propio — los repos bare se materializan
bajo demanda desde storage (app/domain/repo_store.py).
"""

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

from app.api import admin, repos, smart_http
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ca = str(settings.ca_bundle_file) if settings.ca_bundle_file.exists() else None
    app.state.http = build_http_client(ca)
    app.state.settings = settings
    settings.scratch_dir.mkdir(parents=True, exist_ok=True)

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
    app.state.storage = ServiceClient(
        settings.storage_url, settings.service_name, app.state.http, app.state.tokens
    )
    app.state.cicd = ServiceClient(
        settings.cicd_url, settings.service_name, app.state.http, app.state.tokens
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
        if response.status_code == 200:
            return None
        return f"gestor-db devolvió {response.status_code}"
    except Exception as exc:
        return f"gestor-db inalcanzable: {exc}"


async def check_storage() -> str | None:
    try:
        response = await app.state.http.get(
            f"{settings.storage_url}/health", timeout=3.0
        )
        if response.status_code == 200:
            return None
        return f"storage devolvió {response.status_code}"
    except Exception as exc:
        return f"storage inalcanzable: {exc}"


async def check_migrations() -> str | None:
    return await app.state.migrations.ping()


app = create_app(
    settings,
    title="Freya git",
    lifespan=lifespan,
    readiness_checks={
        "gestor_db": check_gestor_db,
        "storage": check_storage,
        "migrations": check_migrations,
    },
)

app.include_router(admin.router)
app.include_router(repos.router)
app.include_router(smart_http.router)
