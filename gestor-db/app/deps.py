"""Dependencias FastAPI de gestor-db."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from freya_common import BadRequest, Forbidden, MissingCredentials, Unauthorized

from app.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def authenticated(request: Request) -> dict[str, Any]:
    """Valida el Bearer entrante y devuelve las claims.

    Modo bootstrap (gdb-03): sólo se acepta el token estático de
    /run/secrets/bootstrap_token. Cualquier otra cosa es 401 — a diferencia
    de la plantilla genérica, aquí el bootstrap NO deja pasar peticiones sin
    verificar, porque este servicio es la única puerta a PostgreSQL.
    """
    settings = get_settings()

    if not settings.auth_enabled:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise MissingCredentials(
                "Falta la cabecera Authorization: Bearer (modo bootstrap)"
            )
        token = header.removeprefix("Bearer ").strip()
        expected = settings.bootstrap_token
        if not expected or not hmac.compare_digest(token, expected):
            raise Unauthorized("Token de bootstrap inválido")
        return {"service": "bootstrap", "permissions": ["*"]}

    # RETORNO Fase 2 (gdb-08): validación JWT (RSA) contra el JWKS de auth.
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise MissingCredentials("Falta la cabecera Authorization: Bearer")

    verifier = request.app.state.verifier
    if verifier is None:
        raise Unauthorized("El verificador de tokens no está inicializado")

    return await verifier.verify(header.removeprefix("Bearer ").strip())


ClaimsDep = Annotated[dict[str, Any], Depends(authenticated)]


@dataclass(frozen=True)
class Caller:
    tenant: str
    service: str


async def caller_context(request: Request, claims: ClaimsDep) -> Caller:
    """Resuelve tenant y servicio llamante (docs/freya-api-contract.md §15.1).

    X-Service-Name es una cabecera, no una credencial: cualquiera podría
    escribirla. El "service" del JWT (identidad real, firmada por auth)
    tiene que coincidir con lo que la cabecera dice ser.
    """
    settings = get_settings()
    tenant = request.headers.get("X-Tenant-Context", "")
    service = request.headers.get("X-Service-Name", "")
    if not tenant:
        raise BadRequest("Falta la cabecera X-Tenant-Context")
    if not service:
        raise BadRequest("Falta la cabecera X-Service-Name")

    if settings.auth_enabled and claims.get("service") != service:
        raise Forbidden(
            "El servicio del token no coincide con X-Service-Name: el JWT "
            "no acredita ser ese servicio",
            details={"claimed_service": service},
        )

    return Caller(tenant=tenant, service=service)


CallerDep = Annotated[Caller, Depends(caller_context)]
