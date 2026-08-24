"""Vista de storage (docs/ROADMAP.md Fase 9, punto 5): proxy delgado sobre
storage/app/api/{buckets,objects}.py."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from freya_common import NotFound, ServiceClient
from pydantic import BaseModel

from app.infra.gateway import client_dep

router = APIRouter(prefix="/api/storage", tags=["storage"])
StorageClient = Annotated[ServiceClient, Depends(client_dep("storage"))]

# Buckets de almacenamiento interno de otros servicios (git, secrets,
# cicd...), no datos de una persona -- fuera del panel por completo, no
# sólo ocultos de la lista: acceder por URL directa tampoco funciona.
_INTERNAL_BUCKETS = {"git", "secrets", "backups", "logs", "artifacts"}


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
    upstream = await client.put(
        f"/storage/buckets/{bucket}", json=body.model_dump()
    )
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
    objects.py:upload): frontend es la única puerta externa hacia objetos,
    así que un tenant externo sube por aquí, nunca hablando con storage
    directo (docs/ARCHITECTURE.md §8)."""
    _assert_visible(bucket)
    headers = {}
    if content_length := request.headers.get("content-length"):
        headers["Content-Length"] = content_length
    if content_type := request.headers.get("content-type"):
        headers["Content-Type"] = content_type
    upstream = await client.put(
        f"/storage/{bucket}/{key}", content=request.stream(), headers=headers
    )
    return ServiceClient.data(upstream)


@router.get("/{bucket}/{key:path}")
async def download_object(bucket: str, key: str, client: StorageClient) -> Response:
    """Descarga directa: los bytes del objeto tal cual, no el sobre JSON --
    igual que hace storage consigo mismo (X-Freya-No-Envelope), porque el
    contenido subido puede resultar ser JSON sin ser una respuesta de esta API."""
    _assert_visible(bucket)
    upstream = await client.get(f"/storage/{bucket}/{key}")
    response = Response(
        content=upstream.content, media_type=upstream.headers.get("content-type")
    )
    response.headers["X-Freya-No-Envelope"] = "1"
    return response
