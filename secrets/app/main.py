"""Punto de entrada de secrets.

Vault de secretos con envelope encryption (docs/ROADMAP.md Fase 3). Pasa
por gestor-db para todo dato, igual que cualquier otro servicio — sólo la
master key vive fuera de la base, en un fichero montado.
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

from app.api import certs as certs_api
from app.api import secrets as secrets_api
from app.config import get_settings
from app.domain.crypto import MasterKey

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ca = str(settings.ca_bundle_file) if settings.ca_bundle_file.exists() else None
    app.state.http = build_http_client(ca)
    app.state.master_key = MasterKey.from_hex_file(settings.master_key_file)

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
    # El ciphertext de cada secreto vive en storage, no en gestor-db (ver
    # app/domain/vault.py) -- storage nunca ve el DEK ni la master key,
    # sólo un blob opaco.
    app.state.storage = ServiceClient(
        settings.storage_url, settings.service_name, app.state.http, app.state.tokens
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
    title="Freya secrets",
    lifespan=lifespan,
    readiness_checks={"gestor_db": check_gestor_db, "migrations": check_migrations},
)

app.include_router(secrets_api.router)
app.include_router(certs_api.router)
