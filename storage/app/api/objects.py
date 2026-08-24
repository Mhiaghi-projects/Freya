"""Objetos (docs/freya-api-contract.md §5.1-5.6).

"/versions" se registra antes que la ruta genérica de objeto: {key:path}
consume el resto de la URL incluidas barras, así que si el orden fuera al
revés, "/storage/b/foo/versions" se leería como key="foo/versions" en vez
de resolver al listado de versiones de "foo".
"""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse
from freya_common import (
    NO_ENVELOPE_HEADER,
    BadRequest,
    Forbidden,
    PayloadTooLarge,
    current_tenant,
    require_permissions,
)

from app.deps import ClaimsDep
from app.domain import blob_store
from app.domain.objects import (
    delete_object,
    get_object_metadata,
    list_objects,
    list_versions,
    put_object,
)

router = APIRouter(tags=["objects"])

# Bucket reservado: el espacio personal de cada usuario autenticado
# (docs/ARCHITECTURE.md §2.1 -- "cada persona pueda usar storage"). No es
# como los demás buckets, propiedad libre de quien tenga write:storage: el
# aislamiento por dueño se aplica aquí mismo, en la API, porque el modelo
# de buckets de storage no tiene noción de "dueño" -- sólo de tenant.
_USER_BUCKET = "users"


def _check_user_bucket_access(bucket: str, key: str, claims: dict) -> None:
    """Sólo un JWT de usuario (no de servicio) puede tocar 'users/', y sólo
    bajo su propio prefijo {user_id}/ -- nunca el de otro usuario, ni un
    servicio actuando en su nombre (nada llama a esto con un token de
    servicio hoy, pero la barrera está aquí para cuando algo lo intente)."""
    if bucket != _USER_BUCKET:
        return
    if claims.get("service"):
        raise Forbidden(
            f"El bucket '{_USER_BUCKET}' es sólo para usuarios, no servicios"
        )
    user_id = claims.get("sub")
    if not user_id or not (key == user_id or key.startswith(f"{user_id}/")):
        raise Forbidden(
            f"Sólo puedes acceder a tu propio espacio en '{_USER_BUCKET}/{{tu_id}}/'"
        )


def _parse_range(range_header: str, size: int) -> tuple[int, int] | None:
    """Parsea "Range: bytes=start-end" (RFC 7233), incluido el sufijo
    "bytes=-N" (últimos N bytes). Un valor malformado o no satisfacible se
    trata como si no hubiera cabecera -- se sirve el objeto completo en vez
    de reventar en 500, mismo criterio "lenient" que curl/navegadores
    esperan de un servidor que no soporta ese caso concreto."""
    if not range_header.startswith("bytes="):
        return None
    start_s, _, end_s = range_header.removeprefix("bytes=").partition("-")
    try:
        if start_s == "":
            if end_s == "":
                return None
            suffix_len = int(end_s)
            start = max(size - suffix_len, 0)
            end = size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s != "" else size - 1
    except ValueError:
        return None
    end = min(end, size - 1)
    if start < 0 or start > end:
        return None
    return start, end


def _resolve_user_bucket_prefix(
    bucket: str, prefix: str | None, claims: dict
) -> str | None:
    """Listar 'users/' fuerza el prefijo al propio espacio -- nunca se
    puede pedir (ni por accidente) el de otro usuario."""
    if bucket != _USER_BUCKET:
        return prefix
    if claims.get("service"):
        raise Forbidden(
            f"El bucket '{_USER_BUCKET}' es sólo para usuarios, no servicios"
        )
    user_id = claims.get("sub")
    if not user_id:
        raise Forbidden(f"El bucket '{_USER_BUCKET}' es sólo para usuarios")
    if prefix and not (prefix == user_id or prefix.startswith(f"{user_id}/")):
        raise Forbidden(
            f"Sólo puedes listar tu propio espacio en '{_USER_BUCKET}/{{tu_id}}/'"
        )
    return prefix or f"{user_id}/"


def _decode_metadata(header_value: str | None) -> str:
    if not header_value:
        return ""
    try:
        base64.b64decode(header_value)
    except binascii.Error as exc:
        raise BadRequest("X-Object-Metadata no es base64 válido") from exc
    return header_value


@router.get("/storage/{bucket}/{key:path}/versions")
async def read_versions(
    bucket: str, key: str, claims: ClaimsDep, request: Request
) -> list[dict]:
    require_permissions(claims, "read:storage")
    _check_user_bucket_access(bucket, key, claims)
    tenant = current_tenant()
    return await list_versions(
        request.app.state.gestor_db, tenant, bucket=bucket, key=key
    )


@router.put("/storage/{bucket}/{key:path}", status_code=201)
async def upload(
    bucket: str,
    key: str,
    claims: ClaimsDep,
    request: Request,
) -> dict:
    require_permissions(claims, "write:storage")
    _check_user_bucket_access(bucket, key, claims)
    settings = request.app.state.settings

    # Rechazo temprano por Content-Length declarado -- una estimación honesta
    # para la cuota (domain/objects.py), no la única defensa: blob_store.write
    # corta la escritura byte a byte si el cuerpo real supera max_upload_bytes
    # aunque Content-Length mienta o falte (transfer-encoding: chunked).
    content_length = int(request.headers.get("content-length") or 0)
    if content_length > settings.max_upload_bytes:
        raise PayloadTooLarge(
            f"El objeto excede el máximo de {settings.max_upload_bytes} bytes",
            details={"max_bytes": settings.max_upload_bytes},
        )

    mime_type = request.headers.get("content-type", "application/octet-stream")
    metadata = _decode_metadata(request.headers.get("x-object-metadata"))
    if_none_match = request.headers.get("if-none-match")

    tenant = current_tenant()
    return await put_object(
        request.app.state.gestor_db,
        tenant,
        settings.data_dir,
        bucket=bucket,
        key=key,
        content_stream=request.stream(),
        content_length_hint=content_length,
        max_bytes=settings.max_upload_bytes,
        mime_type=mime_type,
        metadata=metadata,
        if_none_match=if_none_match,
    )


@router.get("/storage/{bucket}/{key:path}")
async def download(
    bucket: str,
    key: str,
    claims: ClaimsDep,
    request: Request,
    versionId: str | None = Query(default=None),  # noqa: N803 - nombre del contrato
) -> Response:
    require_permissions(claims, "read:storage")
    _check_user_bucket_access(bucket, key, claims)
    tenant = current_tenant()
    meta = await get_object_metadata(
        request.app.state.gestor_db,
        tenant,
        bucket=bucket,
        key=key,
        version_id=versionId,
    )

    range_header = request.headers.get("range")
    headers = {
        "ETag": f'"{meta["etag"]}"',
        "X-Version-Id": meta["version_id"],
        "X-Version-Status": meta["status"],
        # El contenido es el objeto tal cual lo subió quien lo subió, no una
        # respuesta de esta API -- su content-type puede ser
        # "application/json" sin serlo. Evita que EnvelopeMiddleware lo
        # confunda con una respuesta propia y lo envuelva.
        NO_ENVELOPE_HEADER: "1",
    }
    if meta["metadata"]:
        headers["X-Object-Metadata"] = meta["metadata"]

    parsed_range = _parse_range(range_header, meta["size"]) if range_header else None
    if parsed_range is not None:
        start, end = parsed_range
        headers["Content-Range"] = f"bytes {start}-{end}/{meta['size']}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            blob_store.read_range(
                request.app.state.settings.data_dir,
                tenant,
                bucket,
                key,
                meta["version_id"],
                start,
                end,
            ),
            status_code=206,
            media_type=meta["mime_type"],
            headers=headers,
        )

    # El tamaño ya lo sabe gestor-db (meta["size"]) -- no hace falta leer el
    # fichero para calcular Content-Length como antes.
    headers["Content-Length"] = str(meta["size"])
    return StreamingResponse(
        blob_store.read(
            request.app.state.settings.data_dir, tenant, bucket, key, meta["version_id"]
        ),
        status_code=200,
        media_type=meta["mime_type"],
        headers=headers,
    )


@router.head("/storage/{bucket}/{key:path}")
async def head(
    bucket: str,
    key: str,
    claims: ClaimsDep,
    request: Request,
    versionId: str | None = Query(default=None),  # noqa: N803
) -> Response:
    require_permissions(claims, "read:storage")
    _check_user_bucket_access(bucket, key, claims)
    tenant = current_tenant()
    meta = await get_object_metadata(
        request.app.state.gestor_db,
        tenant,
        bucket=bucket,
        key=key,
        version_id=versionId,
    )
    headers = {
        "ETag": f'"{meta["etag"]}"',
        "X-Version-Id": meta["version_id"],
        "X-Version-Status": meta["status"],
        "Content-Length": str(meta["size"]),
        NO_ENVELOPE_HEADER: "1",
    }
    return Response(status_code=200, media_type=meta["mime_type"], headers=headers)


@router.delete("/storage/{bucket}/{key:path}", status_code=204)
async def remove(
    bucket: str,
    key: str,
    claims: ClaimsDep,
    request: Request,
    versionId: str | None = Query(default=None),  # noqa: N803
) -> None:
    require_permissions(claims, "write:storage")
    _check_user_bucket_access(bucket, key, claims)
    tenant = current_tenant()
    await delete_object(
        request.app.state.gestor_db,
        tenant,
        request.app.state.settings.data_dir,
        bucket=bucket,
        key=key,
        version_id=versionId,
    )


@router.get("/storage/{bucket}")
async def list_bucket_objects(
    bucket: str,
    claims: ClaimsDep,
    request: Request,
    prefix: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
) -> dict:
    require_permissions(claims, "read:storage")
    prefix = _resolve_user_bucket_prefix(bucket, prefix, claims)
    tenant = current_tenant()
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    objects = await list_objects(
        request.app.state.gestor_db,
        tenant,
        bucket=bucket,
        prefix=prefix,
        limit=limit,
        offset=offset,
    )
    next_cursor = str(offset + limit) if len(objects) == limit else None
    return {
        "bucket": bucket,
        "prefix": prefix or "",
        "objects": objects,
        "next_cursor": next_cursor,
    }
