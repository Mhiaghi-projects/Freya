"""CA interna (docs/ROADMAP.md Fase 3, punto 4). Permiso separado de
`read:secrets`/`write:secrets`: emitir un certificado es una capacidad
distinta a leer/escribir secretos genéricos, y sólo la necesita
orquestación de infraestructura (freya.ps1 vía freya-ops), nunca un
servicio de aplicación."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant, require_permissions

from app.deps import ClaimsDep
from app.domain.ca import issue_certificate
from app.domain.vault import record_audit

router = APIRouter(tags=["certs"])


@router.post("/certs/{service}/issue")
async def issue(service: str, claims: ClaimsDep, request: Request) -> dict:
    require_permissions(claims, "write:certs")
    tenant = current_tenant()
    result = await issue_certificate(
        request.app.state.gestor_db,
        tenant,
        request.app.state.master_key,
        request.app.state.storage,
        service=service,
    )
    await record_audit(
        request.app.state.gestor_db,
        tenant,
        key=f"cert:{service}",
        action="issue",
        actor_service=str(claims.get("service") or claims.get("sub") or ""),
    )
    return result
