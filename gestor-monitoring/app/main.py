"""Punto de entrada de gestor-monitoring.

Descubre servicios por la etiqueta freya.service (vía el socket de Docker,
sólo lectura), hace scrape de sus /metrics y lo reenvía a VictoriaMetrics,
y golpea su /ready periódicamente para Cloud Health
(docs/freya-api-contract.md §11, docs/ARCHITECTURE.md §4).
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

from app.api import monitoring
from app.config import get_settings
from app.domain.docker_client import DockerClient
from app.domain.health_monitor import HealthMonitor
from app.domain.log_archiver import LogArchiver
from app.domain.scraper import Scraper

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
    app.state.storage = ServiceClient(
        settings.storage_url, settings.service_name, app.state.http, app.state.tokens
    )

    app.state.migrations = MigrationRunner(
        app.state.gestor_db,
        tenant=settings.default_tenant,
        migrations_dir=Path("/srv/migrations"),
    )
    app.state.migrations.start()

    app.state.docker = DockerClient(settings.docker_socket)

    app.state.scraper = Scraper(
        app.state.docker,
        app.state.http,
        settings.metrics_url,
        settings.scrape_interval_seconds,
        settings.scrape_timeout_seconds,
    )
    app.state.scraper.start()

    app.state.health_monitor = HealthMonitor(
        app.state.docker,
        app.state.http,
        app.state.gestor_db,
        settings.default_tenant,
        settings.scrape_interval_seconds,
        settings.scrape_timeout_seconds,
    )
    app.state.health_monitor.start()

    app.state.log_archiver = LogArchiver(
        app.state.docker,
        app.state.storage,
        app.state.gestor_db,
        settings.default_tenant,
        settings.scrape_interval_seconds,
    )
    app.state.log_archiver.start()

    logger.info("servicio arrancado", extra={"version": settings.service_version})
    try:
        yield
    finally:
        await app.state.log_archiver.stop()
        await app.state.health_monitor.stop()
        await app.state.scraper.stop()
        await app.state.docker.aclose()
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


async def check_metrics_backend() -> str | None:
    try:
        response = await app.state.http.get(
            f"{settings.metrics_url}/health", timeout=3.0
        )
        if response.status_code == 200:
            return None
        return f"metrics devolvió {response.status_code}"
    except Exception as exc:
        return f"metrics inalcanzable: {exc}"


async def check_docker_socket() -> str | None:
    try:
        await app.state.docker.list_service_containers()
        return None
    except Exception as exc:
        return f"socket de Docker inalcanzable: {exc}"


async def check_migrations() -> str | None:
    return await app.state.migrations.ping()


app = create_app(
    settings,
    title="Freya gestor-monitoring",
    lifespan=lifespan,
    readiness_checks={
        "gestor_db": check_gestor_db,
        "metrics_backend": check_metrics_backend,
        "docker_socket": check_docker_socket,
        "migrations": check_migrations,
    },
)

app.include_router(monitoring.router)
