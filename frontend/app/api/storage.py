"""Vista de storage (docs/ROADMAP.md Fase 9, punto 5): proxy delgado sobre
storage/app/api/{buckets,objects}.py."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
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

# "Ver árbol de directorios" (pedido explícito del usuario): hasta 3
# niveles de profundidad desde la carpeta actual, sobre como mucho este
# número de objetos -- suficiente para un espacio personal o de proyecto
# normal sin arriesgarse a construir un árbol gigante en memoria.
_TREE_DEPTH = 3
_TREE_OBJECT_LIMIT = 2000


def _assert_visible(bucket: str) -> None:
    if bucket in _INTERNAL_BUCKETS:
        raise NotFound(f"'{bucket}' no es un bucket de usuario")


def _resolve_tenant(bucket: str, project: str | None) -> str:
    """El espacio personal (bucket "users", Mi Drive) vive siempre en el
    tenant "freya" -- es del propio home de la cuenta, no de un proyecto
    (pedido implícito del usuario: la identidad vive en un solo sitio).
    Cualquier otro bucket usa el proyecto elegido en el selector del
    panel."""
    if bucket == "users":
        return "freya"
    return project or "freya"


class BucketCreate(BaseModel):
    versioning: bool = False
    encryption: bool = False
    max_versions: int = 5
    quota_bytes: int | None = None


@router.get("/buckets")
async def list_buckets(client: StorageClient, project: str | None = None) -> list:
    tenant = project or "freya"
    buckets = ServiceClient.data(await client.get("/storage/buckets", tenant=tenant))
    return [b for b in buckets if b["bucket"] not in _INTERNAL_BUCKETS]


@router.put("/buckets/{bucket}", status_code=201)
async def create_bucket(
    bucket: str, body: BucketCreate, client: StorageClient, project: str | None = None
) -> dict:
    _assert_visible(bucket)
    tenant = _resolve_tenant(bucket, project)
    upstream = await client.put(
        f"/storage/buckets/{bucket}", json=body.model_dump(), tenant=tenant
    )
    return ServiceClient.data(upstream)


@router.get("/buckets/{bucket}/usage")
async def bucket_usage(
    bucket: str, client: StorageClient, project: str | None = None
) -> dict:
    _assert_visible(bucket)
    tenant = _resolve_tenant(bucket, project)
    return ServiceClient.data(
        await client.get(f"/storage/buckets/{bucket}/usage", tenant=tenant)
    )


@router.get("/{bucket}/tree")
async def object_tree(
    bucket: str,
    client: StorageClient,
    prefix: str = "",
    project: str | None = None,
) -> dict:
    """Árbol de hasta 3 niveles de profundidad desde `prefix` (pedido
    explícito del usuario, botón "ver árbol de directorios"). Se construye
    aquí, no en storage: list_objects ahí es plano (una lista de keys bajo
    un prefijo) -- storage no tiene noción de "carpeta" ni de
    profundidad, sólo claves con "/" simuladas como tales."""
    _assert_visible(bucket)
    tenant = _resolve_tenant(bucket, project)
    objects: list[dict] = []
    cursor: str | None = None
    while len(objects) < _TREE_OBJECT_LIMIT:
        params: dict[str, str | int] = {"prefix": prefix, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        page = ServiceClient.data(
            await client.get(f"/storage/{bucket}", params=params, tenant=tenant)
        )
        objects.extend(page["objects"])
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return {"prefix": prefix, "tree": _build_tree(objects, prefix)}


def _build_tree(objects: list[dict], prefix: str) -> list[dict]:
    root: dict[str, dict] = {}
    for obj in objects:
        key = obj["key"]
        rel = key[len(prefix) :] if key.startswith(prefix) else key
        parts = [p for p in rel.split("/") if p]
        if not parts:
            continue
        # El placeholder de carpeta vacía (".keep") no debe aparecer como
        # archivo, pero la carpeta que lo contiene sí tiene que verse --
        # si no, una carpeta vacía sería invisible en el árbol.
        is_keep = parts[-1] == ".keep"
        if is_keep:
            parts = parts[:-1]
            if not parts:
                continue
        truncated = len(parts) > _TREE_DEPTH
        parts = parts[:_TREE_DEPTH]
        node = root
        for i, part in enumerate(parts):
            is_file = i == len(parts) - 1 and not truncated and not is_keep
            entry = node.setdefault(
                part, {"name": part, "type": "folder", "children": {}}
            )
            if is_file:
                entry["type"] = "file"
            node = entry["children"]
    return _tree_to_list(root)


def _tree_to_list(node: dict[str, dict]) -> list[dict]:
    result = []
    def _sort_key(entry: dict) -> tuple[bool, str]:
        return (entry["type"] != "folder", entry["name"])

    for entry in sorted(node.values(), key=_sort_key):
        item: dict = {"name": entry["name"], "type": entry["type"]}
        if entry["type"] == "folder":
            item["children"] = _tree_to_list(entry["children"])
        result.append(item)
    return result


@router.get("/{bucket}")
async def list_objects(
    bucket: str,
    client: StorageClient,
    prefix: str = "",
    limit: int = 100,
    cursor: str | None = None,
    project: str | None = None,
) -> dict:
    _assert_visible(bucket)
    tenant = _resolve_tenant(bucket, project)
    params: dict[str, str | int] = {"prefix": prefix, "limit": limit}
    if cursor:
        params["cursor"] = cursor
    return ServiceClient.data(
        await client.get(f"/storage/{bucket}", params=params, tenant=tenant)
    )


@router.put("/{bucket}/{key:path}", status_code=201)
async def upload_object(
    bucket: str,
    key: str,
    client: StorageClient,
    request: Request,
    project: str | None = Query(default=None),
) -> dict:
    """Sube el cuerpo de la petición tal cual a storage, en streaming (nunca
    lo carga entero en memoria aquí -- mismo motivo que storage/app/api/
    objects.py:upload)."""
    _assert_visible(bucket)
    tenant = _resolve_tenant(bucket, project)
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
        tenant=tenant,
    )
    return ServiceClient.data(upstream)


@router.delete("/{bucket}/{key:path}", status_code=204)
async def delete_object(
    bucket: str, key: str, client: StorageClient, project: str | None = None
) -> None:
    _assert_visible(bucket)
    tenant = _resolve_tenant(bucket, project)
    await client.delete(f"/storage/{bucket}/{key}", tenant=tenant)


@router.get("/{bucket}/{key:path}")
async def download_object(
    bucket: str,
    key: str,
    client: StorageClient,
    project: str | None = Query(default=None),
) -> StreamingResponse:
    """Descarga directa: los bytes del objeto tal cual, no el sobre JSON --
    igual que hace storage consigo mismo (X-Freya-No-Envelope), porque el
    contenido subido puede resultar ser JSON sin ser una respuesta de esta
    API. En streaming real (nunca upstream.content: eso leería el archivo
    entero a memoria antes de mandar el primer byte -- justo lo que un
    archivo pesado no puede permitirse con 256M de límite de contenedor)."""
    _assert_visible(bucket)
    tenant = _resolve_tenant(bucket, project)
    stream_cm = client.stream(
        "GET",
        f"/storage/{bucket}/{key}",
        timeout=_TRANSFER_TIMEOUT_SECONDS,
        tenant=tenant,
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
