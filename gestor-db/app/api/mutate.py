"""POST /mutate — insert/update/delete/upsert (docs/freya-api-contract.md §4.2)."""

from __future__ import annotations

import time
from typing import Any

import asyncpg
from fastapi import APIRouter, Request
from freya_common import require_permissions

from app.deps import CallerDep, ClaimsDep
from app.domain.query_builder import (
    build_delete,
    build_insert,
    build_update,
    build_upsert,
)
from app.domain.tenant import resolve_schema
from app.infra.db import parse_rows_affected, translate_pg_error
from app.models.requests import MutateRequest

router = APIRouter(tags=["mutate"])

_BUILDERS = {
    "insert": lambda body: build_insert(
        table=body.table, data=body.data, returning=body.returning
    ),
    "update": lambda body: build_update(
        table=body.table, where=body.where, data=body.data, returning=body.returning
    ),
    "delete": lambda body: build_delete(table=body.table, where=body.where),
    "upsert": lambda body: build_upsert(
        table=body.table,
        data=body.data,
        conflict_target=body.conflict_target,
        returning=body.returning,
    ),
}


@router.post("/mutate")
async def mutate(
    body: MutateRequest, caller: CallerDep, claims: ClaimsDep, request: Request
) -> dict:
    require_permissions(claims, "write:database")
    settings = request.app.state.settings
    schema = resolve_schema(caller.tenant, body.schema_name)
    sql, params = _BUILDERS[body.action](body)

    started = time.perf_counter()
    returning: list[dict[str, Any]] = []
    try:
        async with request.app.state.db.acquire(schema=schema) as conn:
            if body.returning:
                rows = await conn.fetch(
                    sql, *params, timeout=settings.query_timeout_seconds
                )
                affected = len(rows)
                returning = [dict(row) for row in rows]
            else:
                status = await conn.execute(
                    sql, *params, timeout=settings.query_timeout_seconds
                )
                affected = parse_rows_affected(status)
    except asyncpg.PostgresError as exc:
        raise translate_pg_error(exc) from exc

    return {
        "affected_rows": affected,
        "returning": returning,
        "execution_time_ms": round((time.perf_counter() - started) * 1000, 2),
    }
