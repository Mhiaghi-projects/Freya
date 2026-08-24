"""ServiceClient.stream(): debe entregar los bytes sin leerlos enteros a
memoria de una (para archivos pesados, ver docs/DECISIONS.md) y traducir
un error remoto igual que request().

@pytest.mark.asyncio explícito, no asyncio_mode="auto" como en los demás
servicios: el Dockerfile de este paquete copia pyproject.toml a /srv/app
(hermano de /srv/tests, no antecesor -- lo necesita build_artifact para
"pip wheel ." ahí mismo), así que pytest, invocado sobre /srv/tests, nunca
lo encuentra al buscar configuración hacia arriba."""

from __future__ import annotations

import httpx
import pytest

from freya_common import DependencyUnavailable, FreyaError, ServiceClient


def _client(handler) -> ServiceClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ServiceClient("https://freya-storage:8004", "frontend", http)


@pytest.mark.asyncio
async def test_stream_entrega_los_chunks_reales() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hola mundo", headers={"content-type": "text/plain"})

    client = _client(handler)
    chunks = []
    async with client.stream("GET", "/storage/b/k") as response:
        assert response.headers["content-type"] == "text/plain"
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
    assert b"".join(chunks) == b"hola mundo"


@pytest.mark.asyncio
async def test_stream_traduce_error_remoto() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"success": False, "error": {"code": "RESOURCE_NOT_FOUND", "message": "no existe"}},
        )

    client = _client(handler)
    with pytest.raises(FreyaError) as exc_info:
        async with client.stream("GET", "/storage/b/k"):
            pass
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_stream_traduce_fallo_de_red() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no responde")

    client = _client(handler)
    with pytest.raises(DependencyUnavailable):
        async with client.stream("GET", "/storage/b/k"):
            pass
