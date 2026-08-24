"""Aprovisionamiento de tenants nuevos para storage. Sólo role: admin --
no es un acceso por proyecto (TENANT_GRANTABLE_PERMISSIONS de auth), es
una operación de plataforma: crear el espacio de datos de un tenant."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from freya_common import Forbidden

from app.deps import ClaimsDep
from app.domain.provisioning import provision_tenant

router = APIRouter(tags=["admin"])


@router.post("/storage/admin/tenants/{tenant}/provision", status_code=201)
async def provision(tenant: str, claims: ClaimsDep, request: Request) -> dict:
    if claims.get("role") != "admin":
        raise Forbidden("Sólo un admin puede aprovisionar un tenant")
    settings = request.app.state.settings
    return await provision_tenant(
        request.app.state.gestor_db,
        tenant,
        migrations_dir=Path("/srv/migrations"),
        default_max_versions=settings.default_max_versions,
        default_quota_bytes=settings.default_quota_bytes,
    )
