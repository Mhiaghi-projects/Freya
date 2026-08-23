"""Service Catalog y dashboard general (docs/ROADMAP.md Fase 9, puntos 2-3)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import FreyaError, ServiceClient

from app.deps import SettingsDep, WebSessionDep
from app.domain.catalog import SERVICES
from app.infra.gateway import backend_client

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/catalog")
async def catalog(
    session: WebSessionDep, request: Request, settings: SettingsDep
) -> dict:
    """Catálogo estático fusionado con el estado en vivo de
    gestor-monitoring cuando el usuario tiene permiso para verlo -- sin
    ese permiso, se devuelve el catálogo sin estado en vez de fallar entero."""
    live: dict[str, dict] = {}
    if "read:monitoring" in session.claims.get("permissions", []):
        client = backend_client(
            "gestor-monitoring",
            settings=settings,
            http=request.app.state.http,
            access_token=session.access_token,
        )
        try:
            response = await client.get("/monitoring/dashboard")
            for entry in ServiceClient.data(response).get("services", []):
                live[entry["service"]] = entry
        except FreyaError:
            pass

    services = []
    for service in SERVICES:
        status = live.get(service["name"], {}).get("status", "unknown")
        services.append({**service, "status": status})
    return {"services": services}
