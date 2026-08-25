"""Emisión de JWT RSA (docs/freya-api-contract.md §15.1).

Audiencia fija "freya_internal": no hay lista de destinos, el JWT es la
credencial de la malla y los permissions deciden qué puede hacer cada
llamante. El JWT de servicio lleva sub="service_authentication" (constante)
— la identidad real va en la claim "service" — porque así lo fija el
contrato; el JWT de usuario lleva sub=user_id, como es habitual.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
from freya_common import INTERNAL_AUDIENCE

from app.domain.keys import KeyRing

SERVICE_SUBJECT = "service_authentication"


def _issue(
    keyring: KeyRing,
    *,
    subject: str,
    issuer: str,
    ttl_seconds: int,
    extra_claims: dict[str, Any],
) -> tuple[str, int]:
    key = keyring.active
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": issuer,
        "sub": subject,
        "aud": INTERNAL_AUDIENCE,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": str(uuid.uuid4()),
        **extra_claims,
    }
    token = jwt.encode(
        claims, key.private_pem, algorithm="RS256", headers={"kid": key.kid}
    )
    return token, ttl_seconds


def issue_service_token(
    keyring: KeyRing,
    *,
    service: str,
    permissions: list[str],
    issuer: str,
    ttl_seconds: int,
) -> tuple[str, int]:
    return _issue(
        keyring,
        subject=SERVICE_SUBJECT,
        issuer=issuer,
        ttl_seconds=ttl_seconds,
        extra_claims={"service": service, "permissions": permissions},
    )


def issue_tenant_key_token(
    keyring: KeyRing,
    *,
    key_row_id: str,
    tenant_id: str,
    permissions: list[str],
    issuer: str,
    ttl_seconds: int,
) -> tuple[str, int]:
    """JWT de una tenant_api_key ("como las nubes", ver
    app.domain.tenant_keys) -- estructuralmente igual a un JWT de usuario
    (mismo `tenant_grants` que storage/git/cicd/project-manager/gestor-db
    ya saben leer, sin ningún cambio en esos servicios), pero sub es la
    propia key (no hay persona detrás, no hay refresh token: se vuelve a
    pedir con key_id/api_secret cuando expira) y `permissions` plano queda
    siempre vacío -- todo lo que puede hacer viene acotado por
    tenant_grants de un único tenant, nunca un permiso global de la malla."""
    return _issue(
        keyring,
        subject=key_row_id,
        issuer=issuer,
        ttl_seconds=ttl_seconds,
        extra_claims={
            "tenant_id": tenant_id,
            "role": "tenant_key",
            "permissions": [],
            "tenant_grants": {tenant_id: permissions},
        },
    )


def issue_user_token(
    keyring: KeyRing,
    *,
    user_id: str,
    tenant_id: str,
    role: str,
    permissions: list[str],
    issuer: str,
    ttl_seconds: int,
    tenant_grants: dict[str, list[str]] | None = None,
) -> tuple[str, int]:
    # tenant_grants (accesos por proyecto a storage/monitoring, ver
    # app.domain.tenants.py) va congelado en el token igual que
    # `permissions` -- un cambio de un admin se ve recién en el próximo
    # login/refresh, mismo comportamiento que ya tenía extra_permissions.
    return _issue(
        keyring,
        subject=user_id,
        issuer=issuer,
        ttl_seconds=ttl_seconds,
        extra_claims={
            "tenant_id": tenant_id,
            "role": role,
            "permissions": permissions,
            "tenant_grants": tenant_grants or {},
        },
    )
