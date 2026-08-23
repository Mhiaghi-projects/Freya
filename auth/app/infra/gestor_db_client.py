"""Cliente hacia gestor-db: token de bootstrap o JWT propio, según la fase.

Antes del retorno de Fase 2, gestor-db sólo acepta su token estático.
Después, auth firma su propio JWT en proceso con SelfTokenProvider — nunca
pide uno a través de ServiceTokenProvider, que llamaría a su propio
POST /authenticate/service, cuyo handler necesita hablar con gestor-db, que
necesita ese mismo token: un autobloqueo sobre el lock de
ServiceTokenProvider. Cualquier otro servicio sí usará ServiceTokenProvider
sin problema, porque no se autentica contra sí mismo.

gdb_query/gdb_mutate viven en freya_common: los usa cualquier servicio que
hable con gestor-db, no sólo auth.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from freya_common import ServiceClient

from app.domain.keys import KeyRing
from app.domain.tokens import issue_service_token

_RENEW_MARGIN_SECONDS = 30


class StaticTokenProvider:
    """Mismo contrato que ServiceTokenProvider, para el modo bootstrap."""

    def __init__(self, token: str) -> None:
        self._token = token

    async def token(self) -> str:
        return self._token


class SelfTokenProvider:
    """auth firma su propio JWT de servicio en proceso: tiene la clave, no
    necesita pedírselo a nadie (ni a sí misma por HTTP)."""

    def __init__(
        self,
        keyring: KeyRing,
        *,
        service: str,
        permissions: list[str],
        issuer: str,
        ttl_seconds: int,
    ) -> None:
        self._keyring = keyring
        self._service = service
        self._permissions = permissions
        self._issuer = issuer
        self._ttl = ttl_seconds
        self._token = ""
        self._expires_at = 0.0

    async def token(self) -> str:
        if self._token and time.time() < self._expires_at - _RENEW_MARGIN_SECONDS:
            return self._token
        self._token, _ = issue_service_token(
            self._keyring,
            service=self._service,
            permissions=self._permissions,
            issuer=self._issuer,
            ttl_seconds=self._ttl,
        )
        self._expires_at = time.time() + self._ttl
        return self._token


def build_gestor_db_client(
    gestor_db_url: str, service_name: str, http: httpx.AsyncClient, token_provider: Any
) -> ServiceClient:
    return ServiceClient(gestor_db_url, service_name, http, token_provider)
