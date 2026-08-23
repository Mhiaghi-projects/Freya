"""Pipelines (docs/freya-api-contract.md §8, recortado a ROADMAP.md ci-01/02).

Sólo `pipeline_type: standard-tests` existe hoy: un pipeline declarativo en
YAML dentro del repo (ci-02 tal cual la describe el roadmap) implicaría
ejecutar lo que ese YAML defina -- exactamente la superficie de ataque que
se decidió no abrir en esta pasada (ver README). "standard-tests" es el
único tipo, fijo en el propio servicio, nunca definido por quien llama.
"""

from __future__ import annotations

from typing import Any

from freya_common import (
    Conflict,
    NotFound,
    ServiceClient,
    UnprocessableEntity,
    gdb_mutate,
    gdb_query,
    new_id,
)

PIPELINE_TYPES = {"standard-tests"}


async def create_pipeline(
    client: ServiceClient, tenant: str, *, name: str, service: str, pipeline_type: str
) -> dict[str, Any]:
    if pipeline_type not in PIPELINE_TYPES:
        raise UnprocessableEntity(
            f"pipeline_type debe ser uno de {sorted(PIPELINE_TYPES)} en esta fase",
            details={"pipeline_type": pipeline_type},
        )

    existing = await gdb_query(
        client,
        tenant,
        table="ci_pipelines",
        select=["id"],
        where={"name": name, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if existing:
        raise Conflict(f"El pipeline '{name}' ya existe", details={"name": name})

    pipeline_id = new_id("pip")
    await gdb_mutate(
        client,
        tenant,
        table="ci_pipelines",
        action="insert",
        data={
            "id": pipeline_id,
            "name": name,
            "service": service,
            "pipeline_type": pipeline_type,
        },
    )
    return {"pipeline_id": pipeline_id, "name": name, "service": service}


async def get_pipeline(
    client: ServiceClient, tenant: str, *, pipeline_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="ci_pipelines",
        select=["id", "name", "service", "pipeline_type", "created_at"],
        where={"id": pipeline_id, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if not rows:
        raise NotFound(
            f"El pipeline '{pipeline_id}' no existe",
            details={"pipeline_id": pipeline_id},
        )
    return rows[0]


async def list_pipelines(client: ServiceClient, tenant: str) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="ci_pipelines",
        select=["id", "name", "service", "pipeline_type", "created_at"],
        where={"deleted_at": {"is_null": True}},
        order_by=[{"field": "name", "direction": "asc"}],
        limit=200,
    )
