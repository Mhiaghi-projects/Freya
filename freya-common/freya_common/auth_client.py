"""Cliente de autenticación de la malla (docs/freya-api-contract.md §15).

Dos responsabilidades:
  1. Obtener y renovar el JWT de servicio contra `auth`
     (POST /authenticate/service, no expuesto por el gateway).
  2. Validar localmente los JWT entrantes contra la clave pública RSA
     cacheada de `auth`.

Ningún servicio implementa esto por su cuenta.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWK
from jwt.exceptions import PyJWTError

from .errors import DependencyUnavailable, Forbidden, Unauthorized

logger = logging.getLogger(__name__)

# Margen para renovar antes de que caduque de verdad.
_RENEW_MARGIN_SECONDS = 30

# Audiencia fija de todo JWT de servicio — no hay una lista de destinos
# posibles: el JWT es la credencial de la malla, los permissions deciden
# qué puede hacer cada llamante (docs/freya-api-contract.md §15.1).
INTERNAL_AUDIENCE = "freya_internal"


class ServiceTokenProvider:
    """Mantiene vivo el JWT de servicio, renovándolo antes de que expire."""

    def __init__(
        self,
        auth_url: str,
        service_name: str,
        api_key: str,
        api_secret: str,
        http: httpx.AsyncClient,
    ) -> None:
        self._auth_url = auth_url.rstrip("/")
        self._service_name = service_name
        self._api_key = api_key
        self._api_secret = api_secret
        self._http = http
        self._token: str = ""
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        if self._token and time.time() < self._expires_at - _RENEW_MARGIN_SECONDS:
            return self._token
        async with self._lock:
            # Otra corrutina pudo renovarlo mientras esperábamos el lock.
            if self._token and time.time() < self._expires_at - _RENEW_MARGIN_SECONDS:
                return self._token
            await self._fetch()
        return self._token

    async def _fetch(self) -> None:
        try:
            response = await self._http.post(
                f"{self._auth_url}/authenticate/service",
                json={
                    "service": self._service_name,
                    "api_key": self._api_key,
                    "api_secret": self._api_secret,
                },
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise DependencyUnavailable(f"auth no responde: {exc}") from exc

        if response.status_code != 200:
            raise Unauthorized(
                "auth rechazó las credenciales de servicio",
                details={"status": response.status_code},
            )

        data = response.json()["data"]
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 300))
        logger.info("service token renovado", extra={"service": self._service_name})


class JwksCache:
    """Cachea la clave pública de `auth` para validar JWT sin llamada por
    petición. RSA (RS256), no EdDSA — ver docs/freya-api-contract.md §15.1."""

    def __init__(self, auth_url: str, http: httpx.AsyncClient, ttl: int = 600) -> None:
        self._url = f"{auth_url.rstrip('/')}/.well-known/jwks.json"
        self._http = http
        self._ttl = ttl
        self._keys: dict[str, Any] = {}
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def keys(self, force: bool = False) -> dict[str, Any]:
        if not force and self._keys and time.time() - self._fetched_at < self._ttl:
            return self._keys
        async with self._lock:
            if not force and self._keys and time.time() - self._fetched_at < self._ttl:
                return self._keys
            try:
                response = await self._http.get(self._url, timeout=10.0)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                if self._keys:
                    # Preferimos claves rancias a quedarnos sin validar nada.
                    logger.warning("JWKS no accesible, se usa la caché previa")
                    return self._keys
                raise DependencyUnavailable(f"JWKS no accesible: {exc}") from exc
            self._keys = response.json()["data"]
            self._fetched_at = time.time()
        return self._keys


class TokenVerifier:
    """Valida JWT de servicio: firma RSA, audiencia fija "freya_internal",
    issuer "auth"."""

    def __init__(self, jwks: JwksCache, issuer: str) -> None:
        self._jwks = jwks
        self._issuer = issuer

    async def verify(self, token: str) -> dict[str, Any]:
        keys = await self._jwks.keys()
        try:
            return self._decode(token, keys)
        except PyJWTError as exc:
            # Un kid nuevo tras rotación merece un reintento con JWKS fresco.
            keys = await self._jwks.keys(force=True)
            try:
                return self._decode(token, keys)
            except PyJWTError:
                raise Unauthorized(f"token inválido: {exc}") from exc

    def _decode(self, token: str, keys: dict[str, Any]) -> dict[str, Any]:
        # PyJWT no acepta un JWKS entero como clave: hay que localizar la
        # entrada por kid y darle esa sola.
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        jwk_data = next(
            (k for k in keys.get("keys", []) if k.get("kid") == kid), None
        )
        if jwk_data is None:
            raise PyJWTError(f"kid '{kid}' no está en el JWKS")
        signing_key = PyJWK(jwk_data).key
        return jwt.decode(
            token,
            key=signing_key,
            algorithms=["RS256"],
            audience=INTERNAL_AUDIENCE,
            issuer=self._issuer,
        )


def require_permissions(claims: dict[str, Any], *needed: str) -> None:
    """Lanza Forbidden si al token le falta alguno de los permissions."""
    granted = set(claims.get("permissions") or [])
    if "*" in granted:
        return
    missing = [permission for permission in needed if permission not in granted]
    if missing:
        raise Forbidden(
            "Faltan permisos para esta operación",
            details={"missing_permissions": missing},
        )
