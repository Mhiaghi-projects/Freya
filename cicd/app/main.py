"""Punto de entrada de cicd.

Runner de pipelines deliberadamente estrecho (ver app/domain/runner.py y
README): sólo construye y ejecuta la etapa `dev` del Dockerfile de un
servicio conocido -- lint + pytest, exactamente lo que ya hacía
`.\\freya.ps1 test`/`lint` desde PowerShell, ahora ejecutado de verdad
desde aquí. Necesita el socket de Docker en ESCRITURA (a diferencia de
gestor-monitoring, que sólo lee) y el repositorio montado de sólo lectura
como contexto de build.
"""

from __future__ import annotations

import asyncio
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

from app.api import admin, deployments, pipelines
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ca = str(settings.ca_bundle_file) if settings.ca_bundle_file.exists() else None
    app.state.http = build_http_client(ca)
    app.state.settings = settings

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
    # Destino de los artefactos que publica build_artifact (ver
    # app/domain/runs.py) -- bucket "artifacts", nunca ci_jobs.log.
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
        if response.status_code == 200:
            return None
        return f"gestor-db devolvió {response.status_code}"
    except Exception as exc:
        return f"gestor-db inalcanzable: {exc}"


async def check_docker() -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            settings.docker_binary,
            "version",
            "--format",
            "{{.Server.Version}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        if proc.returncode == 0:
            return None
        detail = stderr.decode(errors="replace")
        return f"docker version salió con {proc.returncode}: {detail}"
    except Exception as exc:
        return f"docker inalcanzable: {exc}"


async def check_migrations() -> str | None:
    return await app.state.migrations.ping()


app = create_app(
    settings,
    title="Freya cicd",
    lifespan=lifespan,
    readiness_checks={
        "gestor_db": check_gestor_db,
        "docker": check_docker,
        "migrations": check_migrations,
    },
)

app.include_router(admin.router)
app.include_router(pipelines.router)
app.include_router(deployments.router)
