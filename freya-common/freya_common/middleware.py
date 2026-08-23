"""Middleware común: request id, tenant, servicio, log de acceso.

Cabeceras del contrato interno (docs/freya-api-contract.md §15.1) — servicio
↔ servicio, nunca vistas por fuera del gateway: X-Service-Name identifica al
llamante, X-Tenant-Context el tenant destino. Distintas de las externas
(X-Tenant-ID, X-API-Key) que usará el gateway en la Fase 9.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .context import set_request_id, set_service, set_subject, set_tenant
from .metrics import record_request

logger = logging.getLogger("freya.access")

REQUEST_ID_HEADER = "X-Request-ID"
TENANT_HEADER = "X-Tenant-Context"
SERVICE_HEADER = "X-Service-Name"

# Rutas que no generan log de acceso: el ruido no compensa.
_QUIET_PATHS = {"/health", "/health/deep", "/ready", "/metrics"}


class ContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, default_tenant: str = "freya") -> None:
        super().__init__(app)
        self.default_tenant = default_tenant

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = set_request_id(request.headers.get(REQUEST_ID_HEADER))
        set_tenant(request.headers.get(TENANT_HEADER) or self.default_tenant)
        set_service(request.headers.get(SERVICE_HEADER))
        set_subject(None)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = (time.perf_counter() - started) * 1000
            logger.exception(
                "request failed",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "duration_ms": round(duration, 2),
                },
            )
            raise

        duration = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id

        if request.url.path not in _QUIET_PATHS:
            # Plantilla de ruta ("/tasks/{task_id}"), no la URL cruda: con la
            # URL cruda cada id distinto crearía su propia serie de métrica.
            route = request.scope.get("route")
            path_template = getattr(route, "path", None) or request.url.path
            record_request(
                request.method, path_template, response.status_code, duration / 1000
            )
            logger.info(
                "request",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": round(duration, 2),
                    "caller": request.headers.get(SERVICE_HEADER, ""),
                },
            )
        return response
