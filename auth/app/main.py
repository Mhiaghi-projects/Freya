"""Punto de entrada de auth.

Identidad de Freya: firma JWT RSA, JWKS, autenticación de servicios y de
usuarios. auth no tiene excepción para hablar con la base: pasa por
gestor-db igual que cualquier otro servicio.
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
    ServiceTokenProvider,
    SlidingWindowLimiter,
    TokenVerifier,
    build_http_client,
    create_app,
)

from app.api import admin, auth, jwks, service_auth
from app.config import get_settings
from app.domain.keys import KeyRing
from app.infra.gestor_db_client import (
    SelfTokenProvider,
    StaticTokenProvider,
    build_gestor_db_client,
)
from app.infra.secrets_keys import merge_keys_from_secrets

logger = logging.getLogger(__name__)
settings = get_settings()

_SIGNING_KEY_SYNC_ATTEMPTS = 5
_SIGNING_KEY_SYNC_BACKOFF_SECONDS = 2


async def _sync_signing_keys(app: FastAPI) -> None:
    """Reintenta merge_keys_from_secrets en segundo plano.

    El primer intento, si se hiciera dentro de lifespan antes de yield,
    perdería siempre la carrera contra el propio arranque de Uvicorn:
    secrets necesita llamar de vuelta al JWKS de auth (GET
    /.well-known/jwks.json) para verificar el token que auth acaba de
    firmarse con SelfTokenProvider, y ese JWKS no responde hasta que
    Uvicorn esté escuchando -- lo cual ocurre justo después de que
    lifespan termine de arrancar. Por eso esto corre después del yield,
    con reintentos cortos, igual que MigrationRunner."""
    for attempt in range(_SIGNING_KEY_SYNC_ATTEMPTS):
        await asyncio.sleep(_SIGNING_KEY_SYNC_BACKOFF_SECONDS * (attempt + 1))
        try:
            app.state.keyring = await merge_keys_from_secrets(
                app.state.keyring,
                secrets_url=settings.secrets_url,
                http=app.state.http,
                issuer=settings.auth_url,
                ttl_seconds=settings.access_token_service_ttl_seconds,
            )
            return
        except FreyaError as exc:
            logger.warning(
                "intento %d/%d de sincronizar claves de firma con secrets"
                " falló: %s",
                attempt + 1,
                _SIGNING_KEY_SYNC_ATTEMPTS,
                exc,
            )
    logger.warning(
        "no se pudieron sincronizar claves de firma con secrets,"
        " se sigue solo con la de fichero"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    ca = str(settings.ca_bundle_file) if settings.ca_bundle_file.exists() else None
    app.state.http = build_http_client(ca)
    app.state.keyring = KeyRing.load(settings.signing_keys_dir)

    if settings.auth_enabled:
        # Para llamar a OTROS servicios (secrets, storage...), el patrón
        # normal de la malla. Para gestor-db, ver SelfTokenProvider abajo:
        # ServiceTokenProvider aquí sería un autobloqueo contra sí misma.
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
        gestor_db_tokens = SelfTokenProvider(
            app.state.keyring,
            service=settings.service_name,
            permissions=settings.gestor_db_client_permissions,
            issuer=settings.auth_url,
            ttl_seconds=settings.access_token_service_ttl_seconds,
        )
        # sec-05 extendido: la clave de arranque en disco sigue siendo
        # imprescindible (nada de esto puede pasar sin ella, ver
        # app/infra/secrets_keys.py), pero la rotación en curso vive en
        # secrets -- si hay claves nuevas ahí, se combinan en segundo
        # plano (_sync_signing_keys) una vez Uvicorn esté escuchando.
        signing_key_sync = asyncio.create_task(_sync_signing_keys(app))
    else:
        app.state.tokens = None
        app.state.verifier = None
        gestor_db_tokens = StaticTokenProvider(settings.gestor_db_bootstrap_token)
        signing_key_sync = None
        logger.warning("auth deshabilitado: modo bootstrap")

    app.state.gestor_db = build_gestor_db_client(
        settings.gestor_db_url, settings.service_name, app.state.http, gestor_db_tokens
    )

    app.state.token_rate_limiter = SlidingWindowLimiter(
        max_attempts=settings.token_rate_limit_max_attempts,
        window_seconds=settings.token_rate_limit_window_seconds,
    )
    app.state.password_rate_limiter = SlidingWindowLimiter(
        max_attempts=settings.password_rate_limit_max_attempts,
        window_seconds=settings.password_rate_limit_window_seconds,
    )

    app.state.migrations = MigrationRunner(
        app.state.gestor_db,
        tenant=settings.default_tenant,
        migrations_dir=Path("/srv/migrations"),
    )
    app.state.migrations.start()

    logger.info(
        "servicio arrancado",
        extra={
            "version": settings.service_version,
            "active_kid": app.state.keyring.active.kid,
        },
    )
    try:
        yield
    finally:
        if signing_key_sync is not None:
            signing_key_sync.cancel()
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
    title="Freya auth",
    lifespan=lifespan,
    readiness_checks={"gestor_db": check_gestor_db, "migrations": check_migrations},
)

app.include_router(jwks.router)
app.include_router(service_auth.router)
app.include_router(admin.router)
app.include_router(auth.router, prefix="/api/v1/auth")
