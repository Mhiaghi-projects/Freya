"""Objetos versionados (docs/freya-api-contract.md §5).

El ciclo de vida completo de versiones (archivar tras N, borrar tras M —
§5.6 "retention_policy") es tarea del job programado `storage_lifecycle`
(§13.5), no de esta escritura: PUT sólo archiva o purga la versión anterior
según `versioning` del bucket, nunca recorre todo el historial.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from freya_common import (
    Conflict,
    NotFound,
    ServiceClient,
    gdb_mutate,
    gdb_query,
    new_id,
)

from app.domain import blob_store
from app.domain.buckets import check_quota, get_bucket

_GDB_MAX_LIMIT = 200  # tope de gestor-db para "limit" en /query (§4).


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _query_all(
    client: ServiceClient, tenant: str, *, table: str, select: list[str], where: dict
) -> list[dict[str, Any]]:
    """Pagina sobre gdb_query: el DSL de gestor-db no admite limit > 200."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await gdb_query(
            client,
            tenant,
            table=table,
            select=select,
            where=where,
            limit=_GDB_MAX_LIMIT,
            offset=offset,
        )
        rows.extend(page)
        if len(page) < _GDB_MAX_LIMIT:
            return rows
        offset += _GDB_MAX_LIMIT


async def _object_row(
    client: ServiceClient, tenant: str, *, bucket: str, key: str
) -> dict[str, Any] | None:
    rows = await gdb_query(
        client,
        tenant,
        table="storage_objects",
        select=["id", "current_version_id"],
        where={"bucket": bucket, "key": key, "deleted_at": {"is_null": True}},
        limit=1,
    )
    return rows[0] if rows else None


async def put_object(
    client: ServiceClient,
    tenant: str,
    data_dir: Path,
    *,
    bucket: str,
    key: str,
    content: bytes,
    mime_type: str,
    metadata: str,
    if_none_match: str | None,
) -> dict[str, Any]:
    bucket_row = await get_bucket(client, tenant, bucket=bucket)
    existing = await _object_row(client, tenant, bucket=bucket, key=key)
    if if_none_match == "*" and existing is not None:
        raise Conflict(
            f"'{key}' ya existe en '{bucket}'", details={"bucket": bucket, "key": key}
        )

    await check_quota(client, tenant, bucket=bucket, additional_bytes=len(content))

    version_id = new_id("ver")
    checksum, size = blob_store.write(
        data_dir, tenant, bucket, key, version_id, content
    )

    if existing is None:
        object_id = new_id("obj")
        await gdb_mutate(
            client,
            tenant,
            table="storage_objects",
            action="insert",
            data={
                "id": object_id,
                "bucket": bucket,
                "key": key,
                "current_version_id": version_id,
            },
        )
    else:
        object_id = existing["id"]
        previous_version = existing["current_version_id"]
        if previous_version:
            if bucket_row["versioning"]:
                await gdb_mutate(
                    client,
                    tenant,
                    table="storage_versions",
                    action="update",
                    where={"id": previous_version},
                    data={"status": "ARCHIVED"},
                )
            else:
                await gdb_mutate(
                    client,
                    tenant,
                    table="storage_versions",
                    action="delete",
                    where={"id": previous_version},
                )
                blob_store.delete(data_dir, tenant, bucket, key, previous_version)
        await gdb_mutate(
            client,
            tenant,
            table="storage_objects",
            action="update",
            where={"id": object_id},
            data={"current_version_id": version_id, "updated_at": _now()},
        )

    await gdb_mutate(
        client,
        tenant,
        table="storage_versions",
        action="insert",
        data={
            "id": version_id,
            "object_id": object_id,
            "status": "ACTIVE",
            "size": size,
            "mime_type": mime_type,
            "etag": checksum,
            "metadata": metadata,
        },
    )

    return {
        "bucket": bucket,
        "key": key,
        "version_id": version_id,
        "size": size,
        "mime_type": mime_type,
        "etag": checksum,
        "status": "ACTIVE",
        "created_at": _now(),
    }


async def get_object_metadata(
    client: ServiceClient, tenant: str, *, bucket: str, key: str, version_id: str | None
) -> dict[str, Any]:
    row = await _object_row(client, tenant, bucket=bucket, key=key)
    if row is None:
        raise NotFound(
            f"'{key}' no existe en '{bucket}'", details={"bucket": bucket, "key": key}
        )

    target_version = version_id or row["current_version_id"]
    versions = await gdb_query(
        client,
        tenant,
        table="storage_versions",
        select=["id", "status", "size", "mime_type", "etag", "metadata", "created_at"],
        where={"id": target_version},
        limit=1,
    )
    if not versions or versions[0]["status"] == "DELETED":
        raise NotFound(
            f"La versión de '{key}' no existe o fue borrada",
            details={"bucket": bucket, "key": key, "version_id": target_version},
        )
    version = versions[0]
    return {
        "bucket": bucket,
        "key": key,
        "version_id": version["id"],
        "status": version["status"],
        "size": version["size"],
        "mime_type": version["mime_type"],
        "etag": version["etag"],
        "metadata": version["metadata"],
        "created_at": version["created_at"],
        "is_latest": version["id"] == row["current_version_id"],
    }


async def delete_object(
    client: ServiceClient,
    tenant: str,
    data_dir: Path,
    *,
    bucket: str,
    key: str,
    version_id: str | None,
) -> None:
    row = await _object_row(client, tenant, bucket=bucket, key=key)
    if row is None:
        raise NotFound(
            f"'{key}' no existe en '{bucket}'", details={"bucket": bucket, "key": key}
        )

    if version_id is None:
        versions = await _query_all(
            client,
            tenant,
            table="storage_versions",
            select=["id"],
            where={"object_id": row["id"]},
        )
        for version in versions:
            blob_store.delete(data_dir, tenant, bucket, key, version["id"])
        await gdb_mutate(
            client,
            tenant,
            table="storage_versions",
            action="delete",
            where={"object_id": row["id"]},
        )
        await gdb_mutate(
            client,
            tenant,
            table="storage_objects",
            action="update",
            where={"id": row["id"]},
            data={"deleted_at": _now()},
        )
    else:
        blob_store.delete(data_dir, tenant, bucket, key, version_id)
        await gdb_mutate(
            client,
            tenant,
            table="storage_versions",
            action="delete",
            where={"id": version_id, "object_id": row["id"]},
        )
        if version_id == row["current_version_id"]:
            await gdb_mutate(
                client,
                tenant,
                table="storage_objects",
                action="update",
                where={"id": row["id"]},
                data={"current_version_id": None},
            )


async def list_objects(
    client: ServiceClient,
    tenant: str,
    *,
    bucket: str,
    prefix: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    where: dict[str, Any] = {"bucket": bucket, "deleted_at": {"is_null": True}}
    if prefix:
        where["key"] = {"like": f"{prefix}%"}
    objects = await gdb_query(
        client,
        tenant,
        table="storage_objects",
        select=["id", "key", "current_version_id"],
        where=where,
        order_by=[{"field": "key", "direction": "asc"}],
        limit=limit,
        offset=offset,
    )

    result = []
    for obj in objects:
        if not obj["current_version_id"]:
            continue
        versions = await gdb_query(
            client,
            tenant,
            table="storage_versions",
            select=["size", "mime_type", "etag", "created_at"],
            where={"id": obj["current_version_id"]},
            limit=1,
        )
        if not versions:
            continue
        version = versions[0]
        result.append(
            {
                "key": obj["key"],
                "size": version["size"],
                "mime_type": version["mime_type"],
                "etag": version["etag"],
                "current_version": obj["current_version_id"],
                "last_modified": version["created_at"],
            }
        )
    return result


async def list_versions(
    client: ServiceClient, tenant: str, *, bucket: str, key: str
) -> list[dict[str, Any]]:
    row = await _object_row(client, tenant, bucket=bucket, key=key)
    if row is None:
        raise NotFound(
            f"'{key}' no existe en '{bucket}'", details={"bucket": bucket, "key": key}
        )
    versions = await gdb_query(
        client,
        tenant,
        table="storage_versions",
        select=["id", "status", "size", "created_at"],
        where={"object_id": row["id"]},
        order_by=[{"field": "created_at", "direction": "desc"}],
        limit=200,
    )
    return [
        {
            "version_id": v["id"],
            "status": v["status"],
            "size": v["size"],
            "is_latest": v["id"] == row["current_version_id"],
            "created_at": v["created_at"],
        }
        for v in versions
    ]
