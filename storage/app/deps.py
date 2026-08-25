"""Dependencias FastAPI reutilizables del servicio."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request
from freya_common import (
    Forbidden,
    MissingCredentials,
    Unauthorized,
    require_service_access,
)

from app.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]

# Mismo principio que gestor-monitoring/app/api/monitoring.py
# (_require_project_access): un admin no queda automáticamente habilitado
# para CUALQUIER tenant sólo por tener el permiso plano -- por consistencia
# con "tener un tenant asignado no da ningún permiso por sí solo" (pedido
# explícito del usuario), un admin sólo usa su acceso plano para el tenant
# "freya"; cualquier otro proyecto exige el mismo tenant_grant explícito
# que a cualquier cuenta "user" (hallazgo de una revisión de seguridad:
# antes de esto, un admin sin ningún grant para "athenea" igual podía leer
# su storage con sólo pedir ?project=athenea).
_PLATFORM_TENANT = "freya"


def require_storage_access(
    claims: dict[str, Any], tenant: str, permission: str
) -> None:
    if claims.get("role") == "admin" and tenant != _PLATFORM_TENANT:
        tenant_grants = claims.get("tenant_grants") or {}
        if permission not in set(tenant_grants.get(tenant) or []):
            raise Forbidden(
                "Un admin sin acceso concedido a este proyecto no puede ver su storage",
                details={"missing_permission": permission, "tenant": tenant},
            )
        return
    require_service_access(claims, tenant, permission)


async def authenticated(request: Request) -> dict[str, Any]:
    """Valida el Bearer entrante y devuelve las claims.

    JWT de servicio (docs/freya-api-contract.md §15.1): no lleva tenant —
    la identidad es "service" (mesh-wide) y el tenant de cada petición viaja
    en X-Tenant-Context, no en el token.
    """
    settings = get_settings()
    if not settings.auth_enabled:
        # Modo bootstrap: sujeto sintético, sin permisos reales.
        return {"service": "bootstrap", "permissions": []}

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise MissingCredentials("Falta la cabecera Authorization: Bearer")

    verifier = request.app.state.verifier
    if verifier is None:
        raise Unauthorized("El verificador de tokens no está inicializado")

    return await verifier.verify(header.removeprefix("Bearer ").strip())


ClaimsDep = Annotated[dict[str, Any], Depends(authenticated)]
