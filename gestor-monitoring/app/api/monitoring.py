"""Cloud Health y métricas (docs/freya-api-contract.md §11)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query, Request
from freya_common import Forbidden, NotFound, require_service_access

from app.deps import ClaimsDep
from app.domain import query, services

router = APIRouter(tags=["monitoring"], prefix="/monitoring")

# Tenant reservado de la propia plataforma (freya_common default_tenant) --
# el único que un admin puede mirar aquí (pedido explícito del usuario:
# "admin sólo tiene vista global de Freya"). Cualquier otro proyecto es
# cosa de quien tenga un tenant_grant de monitoring para él, admin incluido
# si algún día se lo concede a sí mismo -- pero no gratis por ser admin.
_PLATFORM_TENANT = "freya"


def _require_project_access(
    claims: dict[str, Any], project: str, permission: str
) -> None:
    if claims.get("role") == "admin":
        if project != _PLATFORM_TENANT:
            raise Forbidden(
                "Un admin sólo ve el monitoreo de la propia plataforma (Freya)",
                details={"tenant": project},
            )
        return
    require_service_access(claims, project, permission)


@router.get("/services")
async def list_all(
    claims: ClaimsDep, request: Request, project: str = Query(default=_PLATFORM_TENANT)
) -> dict:
    _require_project_access(claims, project, "read:monitoring")
    state = request.app.state
    return await services.list_services(
        state.docker,
        state.health_monitor,
        state.gestor_db,
        state.settings.default_tenant,
        project=project,
    )


@router.get("/services/{service}")
async def get_one(
    service: str,
    claims: ClaimsDep,
    request: Request,
    project: str = Query(default=_PLATFORM_TENANT),
) -> dict:
    _require_project_access(claims, project, "read:monitoring")
    state = request.app.state
    return await services.get_service(
        state.docker,
        state.health_monitor,
        state.gestor_db,
        state.settings.default_tenant,
        project=project,
        service=service,
    )


@router.post("/services/{service}/health-check")
async def trigger_health_check(
    service: str,
    claims: ClaimsDep,
    request: Request,
    project: str = Query(default=_PLATFORM_TENANT),
) -> dict:
    _require_project_access(claims, project, "write:monitoring")
    state = request.app.state
    containers = await state.docker.list_service_containers()
    match = next(
        (c for c in containers if c["service"] == service and c["tenant"] == project),
        None,
    )
    if match is None or not match["metrics_port"]:
        raise NotFound(
            f"'{service}' no es un servicio conocido", details={"service": service}
        )
    return await state.health_monitor.check_service(
        service, match["metrics_port"], scheme=match["scheme"]
    )


@router.get("/metrics/{service}")
async def metrics_for_service(
    service: str,
    claims: ClaimsDep,
    request: Request,
    metric: str = Query(...),
    resolution: str = Query(default="5m"),
    since_seconds: int = Query(default=3600, ge=60, le=30 * 24 * 3600),
    project: str = Query(default=_PLATFORM_TENANT),
) -> dict:
    _require_project_access(claims, project, "read:monitoring")
    state = request.app.state
    promql = query.build_promql(metric, service)
    end = int(time.time())
    start = end - since_seconds
    points = await query.query_range(
        state.http,
        state.settings.metrics_url,
        promql=promql,
        start=start,
        end=end,
        resolution=resolution,
    )
    return {
        "service": service,
        "metric": metric,
        "resolution": resolution,
        "points": points,
    }


@router.get("/dashboard")
async def dashboard(
    claims: ClaimsDep, request: Request, project: str = Query(default=_PLATFORM_TENANT)
) -> dict:
    _require_project_access(claims, project, "read:monitoring")
    state = request.app.state
    overview = await services.list_services(
        state.docker,
        state.health_monitor,
        state.gestor_db,
        state.settings.default_tenant,
        project=project,
    )
    return {
        "overall_status": overview["overall_status"],
        "summary": overview["summary"],
        "services": overview["services"],
    }
