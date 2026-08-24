"""Service Catalog y dashboard general (docs/ROADMAP.md Fase 9, puntos 2-3)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from freya_common import FreyaError, ServiceClient

from app.deps import SettingsDep, WebSessionDep
from app.domain.catalog import SERVICES
from app.infra.gateway import backend_client

router = APIRouter(prefix="/api", tags=["catalog"])

# Único proyecto con catálogo curado (los 9 servicios propios de la
# plataforma) -- cualquier otro proyecto no tiene una lista fija, es lo que
# sea que gestor-monitoring encuentre corriendo con esa etiqueta de tenant
# (pedido explícito del usuario: monitoreo por proyecto, ver
# gestor-monitoring/app/api/monitoring.py).
_PLATFORM_TENANT = "freya"


@router.get("/catalog")
async def catalog(
    session: WebSessionDep,
    request: Request,
    settings: SettingsDep,
    project: str = Query(default=_PLATFORM_TENANT),
) -> dict:
    """Monitoreo por proyecto (pedido explícito del usuario): sin acceso a
    `project`, gestor-monitoring devuelve 403 y aquí se traduce en un
    catálogo vacío en vez de reventar -- el panel decide qué mostrar según
    los tenant_grants de /api/session/me, esto es sólo la fuente de datos.

    Para el proyecto "freya" el catálogo son los 9 servicios propios,
    curados, fusionados con su estado en vivo. Para cualquier otro
    proyecto no hay lista fija -- es lo que gestor-monitoring encuentre
    corriendo bajo ese tenant."""
    client = backend_client(
        "gestor-monitoring",
        settings=settings,
        http=request.app.state.http,
        access_token=session.access_token,
    )
    try:
        response = await client.get(
            "/monitoring/dashboard", params={"project": project}
        )
        live_services = ServiceClient.data(response).get("services", [])
    except FreyaError:
        return {"services": []}

    if project != _PLATFORM_TENANT:
        return {"services": live_services}

    live = {entry["service"]: entry for entry in live_services}
    services = []
    for service in SERVICES:
        status = live.get(service["name"], {}).get("status", "unknown")
        services.append({**service, "status": status})
    return {"services": services}
