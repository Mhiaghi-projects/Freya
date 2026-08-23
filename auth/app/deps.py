"""Dependencias FastAPI de auth."""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import Depends, Request
from freya_common import Forbidden, MissingCredentials, Unauthorized

from app.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def admin_principal(request: Request) -> dict[str, Any]:
    """Autoriza /admin/*: token de bootstrap propio mientras
    AUTH_ENABLED=false (no hay JWT posible: aún no existe ninguna cuenta),
    JWT de usuario con role: admin después (docs/freya-api-contract.md §3).
    """
    settings = get_settings()
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise MissingCredentials("Falta la cabecera Authorization: Bearer")
    token = header.removeprefix("Bearer ").strip()

    if not settings.auth_enabled:
        expected = settings.bootstrap_token
        if not expected or not hmac.compare_digest(token, expected):
            raise Unauthorized("Token de bootstrap inválido")
        return {"sub": "bootstrap", "role": "admin"}

    verifier = request.app.state.verifier
    if verifier is None:
        raise Unauthorized("El verificador de tokens no está inicializado")
    claims = await verifier.verify(token)
    if claims.get("role") != "admin":
        raise Forbidden("Se requiere role: admin")
    return claims


AdminDep = Annotated[dict[str, Any], Depends(admin_principal)]


async def user_principal(request: Request) -> dict[str, Any]:
    """Autoriza rutas de autoservicio (/auth/change-password): cualquier JWT
    de usuario válido, sin exigir un role concreto -- a diferencia de
    admin_principal."""
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
    return claims


UserDep = Annotated[dict[str, Any], Depends(user_principal)]
