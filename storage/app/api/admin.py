"""Aprovisionamiento de tenants nuevos para storage. Sólo role: admin --
no es un acceso por proyecto (TENANT_GRANTABLE_PERMISSIONS de auth), es
una operación de plataforma: crear el espacio de datos de un tenant."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from freya_common import BadRequest, Forbidden

from app.deps import ClaimsDep
from app.domain import blob_store
from app.domain.provisioning import provision_tenant

router = APIRouter(tags=["admin"])

# El schema (metadatos) de "freya" nunca se toca por aquí -- ver
# auth/app/domain/tenants.py:delete_tenant, que ya lo bloquea antes de
# llegar a pedir esto. Este segundo bloqueo es defensa en profundidad: aun
# si algo llamara directo a este endpoint, nunca borra los bytes propios
# de la plataforma.
_PLATFORM_TENANT = "freya"


def _require_admin(claims: dict) -> None:
    if claims.get("role") != "admin":
        raise Forbidden("Sólo un admin puede administrar tenants")


@router.post("/storage/admin/tenants/{tenant}/provision", status_code=201)
async def provision(tenant: str, claims: ClaimsDep, request: Request) -> dict:
    _require_admin(claims)
    settings = request.app.state.settings
    return await provision_tenant(
        request.app.state.gestor_db,
        tenant,
        migrations_dir=Path("/srv/migrations"),
        default_max_versions=settings.default_max_versions,
        default_quota_bytes=settings.default_quota_bytes,
    )


@router.delete("/storage/admin/tenants/{tenant}", status_code=204)
async def delete_tenant_data(tenant: str, claims: ClaimsDep, request: Request) -> None:
    """Borra los bytes en disco del tenant (los metadatos ya se fueron con
    el schema, ver auth/app/domain/tenants.py:delete_tenant) -- pedido
    explícito del usuario."""
    _require_admin(claims)
    if tenant == _PLATFORM_TENANT:
        raise BadRequest(f"el tenant '{_PLATFORM_TENANT}' no se puede eliminar")
    blob_store.delete_tenant(request.app.state.settings.data_dir, tenant)
