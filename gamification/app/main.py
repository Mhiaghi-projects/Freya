"""Punto de entrada de gamification (docs/ROADMAP.md Fase 10)."""

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

from app.api import achievements, goals, habits, rewards, stats
from app.config import get_settings
from app.domain.achievements import seed_catalog
from app.domain.github_task_sync import GitHubTaskSyncer
from app.domain.task_sync import TaskSyncer

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
    app.state.project_manager = ServiceClient(
        settings.project_manager_url,
        settings.service_name,
        app.state.http,
        app.state.tokens,
    )

    app.state.migrations = MigrationRunner(
        app.state.gestor_db,
        tenant=settings.default_tenant,
        migrations_dir=Path("/srv/migrations"),
    )
    app.state.migrations.start()

    app.state.task_syncer = TaskSyncer(
        app.state.project_manager,
        app.state.gestor_db,
        settings.default_tenant,
        settings.task_sync_interval_seconds,
    )

    # Apagado por defecto (settings.use_github_task_sync) -- ver
    # app/domain/github_task_sync.py y docs/DECISIONS.md. Usa un "source"
    # distinto al de TaskSyncer en gam_xp_events, así que los dos pueden
    # correr a la vez sin premiar nada dos veces: activarlo no exige apagar
    # el otro en el mismo instante.
    app.state.github_task_syncer = None
    if settings.use_github_task_sync:
        github_configured = (
            settings.github_owner and settings.github_repo_list and settings.github_pat
        )
        if not github_configured:
            logger.warning(
                "use_github_task_sync=true pero falta github_owner/"
                "github_repos/github_pat_file -- sincronización de GitHub "
                "no arranca"
            )
        else:
            app.state.github_task_syncer = GitHubTaskSyncer(
                app.state.http,
                app.state.gestor_db,
                settings.default_tenant,
                github_pat=settings.github_pat,
                owner=settings.github_owner,
                repos=settings.github_repo_list,
                default_user_id=settings.github_default_user_id,
                interval_seconds=settings.task_sync_interval_seconds,
            )

    app.state.seed_task = asyncio.create_task(_seed_and_start_sync(app))

    logger.info("servicio arrancado", extra={"version": settings.service_version})
    try:
        yield
    finally:
        app.state.seed_task.cancel()
        await app.state.task_syncer.stop()
        if app.state.github_task_syncer is not None:
            await app.state.github_task_syncer.stop()
        await app.state.migrations.stop()
        await app.state.http.aclose()
        logger.info("servicio detenido")


async def _seed_and_start_sync(app: FastAPI) -> None:
    """El catálogo de logros y el poll de tasks necesitan el schema ya
    migrado -- esperan a MigrationRunner igual que storage espera para
    crear su bucket "users" (mismo patrón de esta sesión)."""
    for _ in range(60):
        if app.state.migrations.done:
            break
        await asyncio.sleep(1)
    await seed_catalog(app.state.gestor_db, settings.default_tenant)
    app.state.task_syncer.start()
    if app.state.github_task_syncer is not None:
        app.state.github_task_syncer.start()


async def check_project_manager() -> str | None:
    try:
        response = await app.state.http.get(
            f"{settings.project_manager_url}/health", timeout=3.0
        )
        if response.status_code == 200:
            return None
        return f"project-manager devolvió {response.status_code}"
    except Exception as exc:
        return f"project-manager inalcanzable: {exc}"


async def check_migrations() -> str | None:
    return await app.state.migrations.ping()


app = create_app(
    settings,
    title="Freya gamification",
    lifespan=lifespan,
    readiness_checks={
        "project_manager": check_project_manager,
        "migrations": check_migrations,
    },
)

app.include_router(stats.router)
app.include_router(achievements.router)
app.include_router(habits.router)
app.include_router(rewards.router)
app.include_router(goals.router)
