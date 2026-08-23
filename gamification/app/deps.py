"""Dependencias FastAPI reutilizables del servicio."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request
from freya_common import Forbidden, MissingCredentials, Unauthorized

from app.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


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


async def user_id_of(claims: ClaimsDep) -> str:
    """Todas las rutas de gamification son de autoservicio -- gamifican a
    la persona dueña del token, nunca a otra. Un token de servicio no tiene
    un 'yo' que gamificar."""
    if "service" in claims:
        raise Forbidden("Se requiere un token de usuario, no de servicio")
    return claims["sub"]


UserIdDep = Annotated[str, Depends(user_id_of)]
