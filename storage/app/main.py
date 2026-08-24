"""Punto de entrada de storage.

Objetos versionados con bytes en volumen y metadatos en gestor-db
(docs/ROADMAP.md Fase 4). Igual que cualquier otro servicio, pasa por
gestor-db para todo dato — el volumen sólo guarda los bytes en sí.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from freya_common import (
    FreyaError,
    JwksCache,
    MigrationRunner,
    ServiceClient,
    ServiceTokenProvider,
    TokenVerifier,
    build_http_client,
    create_app,
)

from app.api import admin, buckets, objects
from app.config import get_settings
from app.domain.buckets import create_bucket

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ca = str(settings.ca_bundle_file) if settings.ca_bundle_file.exists() else None
    app.state.http = build_http_client(ca)
    app.state.settings = settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)

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

    background_tasks: list[asyncio.Task] = []
    if settings.auth_enabled:
        # En segundo plano: las migraciones de arriba corren en su propia
        # tarea (MigrationRunner.start() no espera a que terminen), así que
        # el bucket "users" tiene que esperar a que la tabla exista de
        # verdad antes de poder crearse -- nunca debe bloquear el arranque
        # del servicio en sí.
        background_tasks.append(asyncio.create_task(_ensure_users_bucket(app)))

    logger.info("servicio arrancado", extra={"version": settings.service_version})
    try:
        yield
    finally:
        for task in background_tasks:
            task.cancel()
        await app.state.migrations.stop()
        await app.state.http.aclose()
        logger.info("servicio detenido")


async def _ensure_users_bucket(app: FastAPI) -> None:
    """Bucket reservado para el espacio personal de cada usuario
    (docs/ARCHITECTURE.md §2.1) -- lo crea storage mismo al arrancar, no
    depende de que alguien lo pida por la API. Reintenta con backoff hasta
    que las migraciones hayan corrido (la tabla storage_buckets tiene que
    existir), 409 si ya existe no es un error."""
    delay = 1.0
    while not app.state.migrations.done:
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30.0)
    try:
        await create_bucket(
            app.state.gestor_db,
            settings.default_tenant,
            bucket="users",
            versioning=False,
            encryption=False,
            max_versions=settings.default_max_versions,
            quota_bytes=settings.default_quota_bytes,
        )
        logger.info("bucket 'users' creado")
    except FreyaError as exc:
        if exc.status_code != 409:
            logger.warning(
                "no se pudo crear el bucket 'users'", extra={"error": str(exc)}
            )


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
    title="Freya storage",
    lifespan=lifespan,
    readiness_checks={"gestor_db": check_gestor_db, "migrations": check_migrations},
)

# admin y buckets ANTES que objects: "/storage/buckets" y "/storage/{bucket}"
# tienen la misma forma (un segmento tras /storage) — sin este orden,
# "buckets" (o "admin") se leería como el nombre de un bucket.
app.include_router(admin.router)
app.include_router(buckets.router)
app.include_router(objects.router)
