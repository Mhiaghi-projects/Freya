"""Dependencias FastAPI reutilizables del servicio."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request
from freya_common import Forbidden, MissingCredentials, Unauthorized
from freya_common.context import current_tenant

from app.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def user_principal(request: Request) -> dict[str, Any]:
    """Cualquier JWT de usuario válido del tenant actual -- Athenea no tiene
    su propio esquema de roles todavía, así que cualquier usuario puede
    gestionar sus propias páginas (mismo patrón que auth/app/deps.py:
    user_principal, sin exigir un role concreto)."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise MissingCredentials("Falta la cabecera Authorization: Bearer")
    token = header.removeprefix("Bearer ").strip()

    verifier = request.app.state.verifier
    if verifier is None:
        raise Unauthorized("El verificador de tokens no está inicializado")
    claims = await verifier.verify(token)
    if "service" in claims:
        raise Forbidden("Se requiere un token de usuario, no de servicio")
    if claims.get("tenant_id") != current_tenant():
        raise Forbidden("El token no pertenece a este tenant")
    return claims


UserDep = Annotated[dict[str, Any], Depends(user_principal)]
