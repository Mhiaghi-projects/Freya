"""Trae las claves de firma que vivan en secrets (rotación gestionada
desde ahí, ROADMAP.md sec-05 extendido) y las combina con la del fichero
de arranque -- ver docs/ARCHITECTURE.md §2.1 y services/secrets/README.md
para el porqué de que la PRIMERA clave nunca pueda salir de un fichero:
auth necesita firmar su propio JWT (incluso el que usaría para llamar a
secrets) antes de que exista ninguna llamada HTTPS posible.

Por eso este módulo nunca se ejecuta antes de que `KeyRing.load()` ya haya
cargado al menos una clave del fichero: usa esa clave (SelfTokenProvider,
el mismo patrón que auth ya usa para hablar con gestor-db) para
autenticarse contra secrets, sin ningún salto HTTP a sí mismo.
"""

from __future__ import annotations

import logging

import httpx
from freya_common import FreyaError, NotFound, ServiceClient

from app.domain.keys import KeyRing, SigningKey, key_from_pem
from app.infra.gestor_db_client import SelfTokenProvider

logger = logging.getLogger(__name__)

_PREFIX = "auth/signing_keys/"


async def merge_keys_from_secrets(
    keyring: KeyRing,
    *,
    secrets_url: str,
    http: httpx.AsyncClient,
    issuer: str,
    ttl_seconds: int,
) -> KeyRing:
    tokens = SelfTokenProvider(
        keyring,
        service="auth",
        permissions=["read:secrets"],
        issuer=issuer,
        ttl_seconds=ttl_seconds,
    )
    client = ServiceClient(secrets_url, "auth", http, tokens)

    # Sin try/except aquí: si secrets no es alcanzable (típicamente porque
    # el propio auth aún no escucha -- ver app/main.py, _sync_signing_keys,
    # secrets necesita el JWKS de auth para verificar este mismo token),
    # que se propague. El reintento con backoff vive en el llamador.
    entries = await client.get("/secrets/freya")
    names = [
        e["key"] for e in ServiceClient.data(entries) if e["key"].startswith(_PREFIX)
    ]

    extra: list[tuple[str, SigningKey]] = []
    for name in names:
        try:
            response = await client.get(f"/secrets/freya/{name}")
            data = ServiceClient.data(response)
            key = key_from_pem(data["value"].encode("utf-8"))
            extra.append((data["created_at"], key))
        except (FreyaError, NotFound, ValueError) as exc:
            logger.warning("clave de firma '%s' en secrets ilegible: %s", name, exc)

    if not extra:
        return keyring
    merged = keyring.merge(extra)
    logger.info(
        "claves de firma combinadas con secrets",
        extra={"desde_secrets": len(extra), "total": len(merged.jwks()["keys"])},
    )
    return merged
