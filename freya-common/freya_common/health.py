"""Endpoints operativos: /health, /ready y /metrics.

/health nunca toca red ni base de datos: es el healthcheck de Docker.
/ready comprueba dependencias y es lo que consulta gestor-monitoring para
Cloud Health. /metrics expone lo que gestor-monitoring hace scrape.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.responses import Response

from .metrics import metrics_response

# Una comprobación devuelve None si está bien, o un mensaje si falla.
ReadinessCheck = Callable[[], Awaitable[str | None]]


def build_router(
    service_name: str,
    version: str,
    checks: dict[str, ReadinessCheck] | None = None,
) -> APIRouter:
    router = APIRouter()
    checks = checks or {}
    started_at = time.time()

    @router.get("/health", include_in_schema=False)
    async def health() -> dict[str, object]:
        # Forma de docs/freya-api-contract.md §14. Sin sobre success/data:
        # /health, /ready y /metrics quedan fuera de /api/v1 a propósito.
        return {
            "status": "healthy",
            "service": service_name,
            "version": version,
            "uptime_seconds": int(time.time() - started_at),
        }

    @router.get("/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        results: dict[str, str] = {}
        healthy = True

        async def run(name: str, check: ReadinessCheck) -> None:
            nonlocal healthy
            try:
                problem = await asyncio.wait_for(check(), timeout=3.0)
            except TimeoutError:
                problem = "timeout tras 3s"
            except Exception as exc:  # una dependencia caída no tumba /ready
                problem = f"{type(exc).__name__}: {exc}"
            if problem is None:
                results[name] = "ok"
            else:
                results[name] = problem
                healthy = False

        await asyncio.gather(*(run(n, c) for n, c in checks.items()))

        return JSONResponse(
            status_code=200 if healthy else 503,
            content={
                "status": "ready" if healthy else "not_ready",
                "service": service_name,
                "version": version,
                "checks": results,
            },
        )

    @router.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return metrics_response()

    return router
