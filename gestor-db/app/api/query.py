"""POST /query — lectura estructurada (docs/freya-api-contract.md §4.1)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from app.deps import CallerDep, ClaimsDep, require_db_access
from app.domain.query_builder import build_select
from app.domain.tenant import resolve_schema
from app.infra.db import PG_ERRORS, translate_pg_error
from app.models.requests import QueryRequest

router = APIRouter(tags=["query"])


@router.post("/query")
async def query(
    body: QueryRequest, caller: CallerDep, claims: ClaimsDep, request: Request
) -> dict:
    require_db_access(claims, caller, "read:database")
    settings = request.app.state.settings
    schema = resolve_schema(caller.tenant, body.schema_name)

    order_by = (
        [item.model_dump() for item in body.order_by] if body.order_by else None
    )
    sql, params = build_select(
        table=body.table,
        select=body.select,
        where=body.where,
        order_by=order_by,
        limit=body.limit,
        offset=body.offset,
    )

    started = time.perf_counter()
    try:
        async with request.app.state.db.acquire(schema=schema) as conn:
            rows = await conn.fetch(
                sql, *params, timeout=settings.query_timeout_seconds
            )
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc

    return {
        "rows": [dict(row) for row in rows],
        "row_count": len(rows),
        "execution_time_ms": round((time.perf_counter() - started) * 1000, 2),
    }
