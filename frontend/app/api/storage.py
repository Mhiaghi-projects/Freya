"""Vista de storage (docs/ROADMAP.md Fase 9, punto 5): proxy delgado sobre
storage/app/api/{buckets,objects}.py."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from freya_common import NotFound, ServiceClient
from pydantic import BaseModel

from app.infra.gateway import client_dep

router = APIRouter(prefix="/api/storage", tags=["storage"])
StorageClient = Annotated[ServiceClient, Depends(client_dep("storage"))]

# Buckets de almacenamiento interno de otros servicios (git, secrets,
# cicd...), no datos de una persona -- fuera del panel por completo, no
# sólo ocultos de la lista: acceder por URL directa tampoco funciona.
_INTERNAL_BUCKETS = {"git", "secrets", "backups", "logs", "artifacts"}

# Subidas/descargas de archivos pesados (pedido explícito del usuario) no
# caben en el timeout por defecto de ServiceClient (30s, pensado para
# llamadas de API normales) -- una hora es margen de sobra incluso para un
# archivo grande en una conexión lenta, sin dejarlo colgado para siempre
# si algo se atasca de verdad.
_TRANSFER_TIMEOUT_SECONDS = 3600.0


def _assert_visible(bucket: str) -> None:
    if bucket in _INTERNAL_BUCKETS:
        raise NotFound(f"'{bucket}' no es un bucket de usuario")


class BucketCreate(BaseModel):
    versioning: bool = False
    encryption: bool = False
    max_versions: int = 5
    quota_bytes: int | None = None


@router.get("/buckets")
async def list_buckets(client: StorageClient) -> list:
    buckets = ServiceClient.data(await client.get("/storage/buckets"))
    return [b for b in buckets if b["bucket"] not in _INTERNAL_BUCKETS]


@router.put("/buckets/{bucket}", status_code=201)
async def create_bucket(bucket: str, body: BucketCreate, client: StorageClient) -> dict:
    _assert_visible(bucket)
    upstream = await client.put(f"/storage/buckets/{bucket}", json=body.model_dump())
    return ServiceClient.data(upstream)


@router.get("/buckets/{bucket}/usage")
async def bucket_usage(bucket: str, client: StorageClient) -> dict:
    _assert_visible(bucket)
    return ServiceClient.data(await client.get(f"/storage/buckets/{bucket}/usage"))


@router.get("/{bucket}")
async def list_objects(
    bucket: str,
    client: StorageClient,
    prefix: str = "",
    limit: int = 100,
    cursor: str | None = None,
) -> dict:
    _assert_visible(bucket)
    params: dict[str, str | int] = {"prefix": prefix, "limit": limit}
    if cursor:
        params["cursor"] = cursor
    return ServiceClient.data(await client.get(f"/storage/{bucket}", params=params))


@router.put("/{bucket}/{key:path}", status_code=201)
async def upload_object(
    bucket: str, key: str, client: StorageClient, request: Request
) -> dict:
    """Sube el cuerpo de la petición tal cual a storage, en streaming (nunca
    lo carga entero en memoria aquí -- mismo motivo que storage/app/api/
    objects.py:upload)."""
    _assert_visible(bucket)
    headers = {}
    if content_length := request.headers.get("content-length"):
        headers["Content-Length"] = content_length
    if content_type := request.headers.get("content-type"):
        headers["Content-Type"] = content_type
    upstream = await client.put(
        f"/storage/{bucket}/{key}",
        content=request.stream(),
        headers=headers,
        timeout=_TRANSFER_TIMEOUT_SECONDS,
    )
    return ServiceClient.data(upstream)


@router.delete("/{bucket}/{key:path}", status_code=204)
async def delete_object(bucket: str, key: str, client: StorageClient) -> None:
    _assert_visible(bucket)
    await client.delete(f"/storage/{bucket}/{key}")


@router.get("/{bucket}/{key:path}")
async def download_object(
    bucket: str, key: str, client: StorageClient
) -> StreamingResponse:
    """Descarga directa: los bytes del objeto tal cual, no el sobre JSON --
    igual que hace storage consigo mismo (X-Freya-No-Envelope), porque el
    contenido subido puede resultar ser JSON sin ser una respuesta de esta
    API. En streaming real (nunca upstream.content: eso leería el archivo
    entero a memoria antes de mandar el primer byte -- justo lo que un
    archivo pesado no puede permitirse con 256M de límite de contenedor)."""
    _assert_visible(bucket)
    stream_cm = client.stream(
        "GET", f"/storage/{bucket}/{key}", timeout=_TRANSFER_TIMEOUT_SECONDS
    )
    upstream = await stream_cm.__aenter__()

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await stream_cm.__aexit__(None, None, None)

    headers = {"X-Freya-No-Envelope": "1"}
    if content_length := upstream.headers.get("content-length"):
        headers["Content-Length"] = content_length
    return StreamingResponse(
        body(), media_type=upstream.headers.get("content-type"), headers=headers
    )
