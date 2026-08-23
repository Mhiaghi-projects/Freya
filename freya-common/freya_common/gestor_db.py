"""Helpers para hablar con gestor-db usando su DSL estructurado
(docs/freya-api-contract.md §4). Todo servicio que necesite datos pasa por
aquí — nunca SQL crudo, nunca una conexión directa a PostgreSQL.
"""

from __future__ import annotations

from typing import Any

from .http import ServiceClient


async def gdb_query(
    client: ServiceClient,
    tenant: str,
    *,
    table: str,
    select: list[str] | None = None,
    where: dict[str, Any] | None = None,
    order_by: list[dict[str, str]] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    body: dict[str, Any] = {
        "schema": tenant,
        "table": table,
        "limit": limit,
        "offset": offset,
    }
    if select is not None:
        body["select"] = select
    if where is not None:
        body["where"] = where
    if order_by is not None:
        body["order_by"] = order_by
    response = await client.post("/query", tenant=tenant, json=body)
    return ServiceClient.data(response)["rows"]


async def gdb_mutate(
    client: ServiceClient,
    tenant: str,
    *,
    table: str,
    action: str,
    where: dict[str, Any] | None = None,
    data: dict[str, Any] | list[dict[str, Any]] | None = None,
    returning: list[str] | None = None,
    conflict_target: list[str] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"schema": tenant, "table": table, "action": action}
    if where is not None:
        body["where"] = where
    if data is not None:
        body["data"] = data
    if returning is not None:
        body["returning"] = returning
    if conflict_target is not None:
        body["conflict_target"] = conflict_target
    response = await client.post("/mutate", tenant=tenant, json=body)
    return ServiceClient.data(response)
