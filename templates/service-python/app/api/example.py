"""Router de ejemplo. Bórralo al implementar el servicio de verdad.

Muestra el patrón: dependencia de autenticación, comprobación de permisos,
uso del contexto de tenant y del formato de error común.
"""

from __future__ import annotations

from fastapi import APIRouter
from freya_common import NotFound, current_request_id, current_tenant, require_permissions

from app.deps import ClaimsDep

router = APIRouter(tags=["example"])


@router.get("/example")
async def read_example(claims: ClaimsDep) -> dict[str, str]:
    require_permissions(claims, "read:__SERVICE_NAME__")
    return {
        "tenant": current_tenant(),
        "service": str(claims.get("service", "")),
        "request_id": current_request_id(),
    }


@router.get("/example/{item_id}")
async def read_item(item_id: str, claims: ClaimsDep) -> dict[str, str]:
    require_permissions(claims, "read:__SERVICE_NAME__")
    raise NotFound(
        f"El elemento '{item_id}' no existe en el tenant '{current_tenant()}'",
        details={"item_id": item_id, "tenant": current_tenant()},
    )
