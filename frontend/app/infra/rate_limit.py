"""Rate limiting por tenant en el gateway (docs/ROADMAP.md Fase 11).

Se aplica en frontend, no en cada backend por separado, porque frontend es
el único punto por el que entra tráfico externo (services/traefik/) -- un
backend individual nunca ve una petición que no haya pasado ya por aquí.
Clave = tenant (X-Tenant-Context, mismo mecanismo que ContextMiddleware de
freya_common ya usa para todo lo demás), no usuario ni IP: hoy sólo existe
el tenant "freya" (single-tenant en la práctica), así que esto protege el
caso multi-tenant futuro sin inventar todavía un límite por usuario que
nadie ha pedido -- ver docs/DECISIONS.md.
"""

from __future__ import annotations

from freya_common import RateLimited
from freya_common.middleware import TENANT_HEADER
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Rutas fuera del rate limit: son el contrato operativo de Docker/monitoring
# (freya_common.envelope._UNWRAPPED_PATHS), y el propio SPA estático -- sólo
# /api/* es tráfico de negocio real.
_EXEMPT_PREFIXES = ("/health", "/ready", "/metrics", "/app/")


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        tenant = request.headers.get(TENANT_HEADER) or "freya"
        try:
            self._limiter.check(tenant)
        except RateLimited as exc:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": exc.message,
                        "details": exc.details,
                    },
                    "meta": {},
                },
            )
        return await call_next(request)
