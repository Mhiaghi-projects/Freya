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


def issue_user_token(
    keyring: KeyRing,
    *,
    user_id: str,
    tenant_id: str,
    role: str,
    permissions: list[str],
    issuer: str,
    ttl_seconds: int,
) -> tuple[str, int]:
    return _issue(
        keyring,
        subject=user_id,
        issuer=issuer,
        ttl_seconds=ttl_seconds,
        extra_claims={"tenant_id": tenant_id, "role": role, "permissions": permissions},
    )
