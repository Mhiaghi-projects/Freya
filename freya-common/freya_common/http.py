"""Cliente HTTPS para hablar con otros servicios de la malla.

Añade solo las cabeceras obligatorias, adjunta el token de servicio y traduce
el formato de error de Freya a excepciones locales.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .context import current_request_id, current_tenant
from .errors import DependencyUnavailable, FreyaError

logger = logging.getLogger(__name__)


class ServiceClient:
    def __init__(
        self,
        base_url: str,
        service_name: str,
        http: httpx.AsyncClient,
        token_provider: Any | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_name = service_name
        self._http = http
        self._token_provider = token_provider

    async def _headers(self, tenant: str | None) -> dict[str, str]:
        headers = {
            "X-Request-ID": current_request_id(),
            "X-Tenant-Context": tenant or current_tenant() or "freya",
            "X-Service-Name": self._service_name,
        }
        if self._token_provider is not None:
            headers["Authorization"] = f"Bearer {await self._token_provider.token()}"
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        tenant: str | None = None,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        # Las cabeceras de identidad (X-Request-ID, X-Tenant-Context,
        # X-Service-Name, Authorization) siempre ganan: un caller no puede
        # suplantar la identidad del servicio pasando "headers" propio.
        merged = {**(headers or {}), **await self._headers(tenant)}
        try:
            response = await self._http.request(
                method,
                url,
                headers=merged,
                timeout=timeout,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise DependencyUnavailable(
                f"{self._base_url} no responde: {exc}",
                details={"url": url, "method": method},
            ) from exc

        if response.status_code >= 400:
            raise self._translate(response)
        return response

    def _translate(self, response: httpx.Response) -> FreyaError:
        """Convierte el error remoto (sobre {success:false, error}) en una
        excepción con el mismo código."""
        try:
            body = response.json()["error"]
            return FreyaError(
                body.get("message", "error remoto"),
                code=body.get("code", "UPSTREAM_ERROR"),
                status_code=response.status_code,
                details=body.get("details"),
            )
        except (ValueError, KeyError, TypeError):
            return FreyaError(
                f"Respuesta no interpretable de {self._base_url}",
                code="UPSTREAM_ERROR",
                status_code=response.status_code,
            )

    @staticmethod
    def data(response: httpx.Response) -> Any:
        """Desenvuelve el "data" del sobre {success, data, meta} de una
        respuesta ya validada (status < 400, ver request())."""
        return response.json()["data"]

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", path, **kwargs)


def build_http_client(ca_bundle: str | None = None) -> httpx.AsyncClient:
    """Cliente httpx que confía en la CA interna de Freya."""
    return httpx.AsyncClient(
        verify=ca_bundle if ca_bundle else True,
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=8),
        follow_redirects=False,
    )
