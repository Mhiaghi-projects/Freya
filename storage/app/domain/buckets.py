"""Buckets: alta, listado, borrado, uso (docs/freya-api-contract.md §5.9)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from freya_common import (
    Conflict,
    NotFound,
    QuotaExceeded,
    ServiceClient,
    gdb_mutate,
    gdb_query,
    new_id,
)

from app.domain import blob_store


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_bucket(
    client: ServiceClient,
    tenant: str,
    *,
    bucket: str,
    versioning: bool,
    encryption: bool,
    max_versions: int,
    quota_bytes: int,
) -> dict[str, Any]:
    existing = await gdb_query(
        client,
        tenant,
        table="storage_buckets",
        select=["id"],
        where={"bucket": bucket, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if existing:
        raise Conflict(f"El bucket '{bucket}' ya existe", details={"bucket": bucket})

    await gdb_mutate(
        client,
        tenant,
        table="storage_buckets",
        action="insert",
        data={
            "id": new_id("bkt"),
            "bucket": bucket,
            "versioning": versioning,
            "encryption": encryption,
            "max_versions": max_versions,
            "quota_bytes": quota_bytes,
        },
    )
    return {
        "bucket": bucket,
        "versioning": versioning,
        "encryption": encryption,
        "max_versions": max_versions,
        "quota_bytes": quota_bytes,
        "created_at": _now(),
    }


async def get_bucket(
    client: ServiceClient, tenant: str, *, bucket: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="storage_buckets",
        select=["id", "bucket", "versioning", "max_versions", "quota_bytes"],
        where={"bucket": bucket, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if not rows:
        raise NotFound(f"El bucket '{bucket}' no existe", details={"bucket": bucket})
    return rows[0]


async def list_buckets(client: ServiceClient, tenant: str) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="storage_buckets",
        select=["bucket", "versioning", "max_versions", "quota_bytes", "created_at"],
        where={"deleted_at": {"is_null": True}},
        limit=200,
    )


async def delete_bucket(
    client: ServiceClient, tenant: str, data_dir: Path, *, bucket: str, force: bool
) -> None:
    row = await get_bucket(client, tenant, bucket=bucket)
    objects = await _query_all(
        client,
        tenant,
        table="storage_objects",
        select=["id", "key"],
        where={"bucket": bucket, "deleted_at": {"is_null": True}},
    )
    if objects and not force:
        raise Conflict(
            f"El bucket '{bucket}' no está vacío; usa ?force=true",
            details={"bucket": bucket},
        )

    for obj in objects:
        versions = await _query_all(
            client,
            tenant,
            table="storage_versions",
            select=["id"],
            where={"object_id": obj["id"]},
        )
        for version in versions:
            blob_store.delete(data_dir, tenant, bucket, obj["key"], version["id"])
        await gdb_mutate(
            client,
            tenant,
            table="storage_versions",
            action="delete",
            where={"object_id": obj["id"]},
        )
        await gdb_mutate(
            client,
            tenant,
            table="storage_objects",
            action="update",
            where={"id": obj["id"]},
            data={"deleted_at": _now()},
        )

    await gdb_mutate(
        client,
        tenant,
        table="storage_buckets",
        action="update",
        where={"id": row["id"]},
        data={"deleted_at": _now()},
    )


_GDB_MAX_LIMIT = 200  # tope de gestor-db para "limit" en /query (§4).


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


async def bucket_usage(
    client: ServiceClient, tenant: str, *, bucket: str
) -> dict[str, Any]:
    # Recorre objeto por objeto: gestor-db no ofrece SUM/GROUP BY todavía
    # (§4 no lo define). Vale para el tamaño de despliegue de hoy; con
    # muchos objetos, esto pide un contador de uso mantenido de forma
    # incremental en vez de recalcularlo entero en cada lectura.
    row = await get_bucket(client, tenant, bucket=bucket)
    objects = await _query_all(
        client,
        tenant,
        table="storage_objects",
        select=["id"],
        where={"bucket": bucket, "deleted_at": {"is_null": True}},
    )
    total = 0
    active = 0
    for obj in objects:
        versions = await _query_all(
            client,
            tenant,
            table="storage_versions",
            select=["size", "status"],
            where={"object_id": obj["id"]},
        )
        for version in versions:
            total += version["size"]
            if version["status"] == "ACTIVE":
                active += version["size"]

    quota = row["quota_bytes"]
    return {
        "bucket": bucket,
        "object_count": len(objects),
        "total_size_bytes": total,
        "active_size_bytes": active,
        "archived_size_bytes": total - active,
        "quota_bytes": quota,
        "usage_percent": round((total / quota) * 100, 2) if quota else 0.0,
    }


async def check_quota(
    client: ServiceClient,
    tenant: str,
    *,
    bucket: str,
    additional_bytes: int,
    bytes_to_free: int = 0,
) -> None:
    usage = await bucket_usage(client, tenant, bucket=bucket)
    projected = usage["total_size_bytes"] - bytes_to_free + additional_bytes
    if projected > usage["quota_bytes"]:
        raise QuotaExceeded(
            f"El bucket '{bucket}' alcanzó su cuota",
            details={"bucket": bucket, "quota_bytes": usage["quota_bytes"]},
        )
