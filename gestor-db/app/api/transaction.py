"""POST /transaction — varias operaciones atómicas (docs/freya-api-contract.md §4.3)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from freya_common import new_id

from app.deps import CallerDep, ClaimsDep, require_db_access
from app.domain.query_builder import (
    build_delete,
    build_insert,
    build_update,
    build_upsert,
)
from app.domain.tenant import resolve_schema
from app.infra.db import PG_ERRORS, parse_rows_affected, translate_pg_error
from app.models.requests import Operation, TransactionRequest

router = APIRouter(tags=["transaction"])

_BUILDERS = {
    "insert": lambda op: build_insert(
        table=op.table, data=op.data, returning=op.returning
    ),
    "update": lambda op: build_update(
        table=op.table, where=op.where, data=op.data, returning=op.returning
    ),
    "delete": lambda op: build_delete(table=op.table, where=op.where),
    "upsert": lambda op: build_upsert(
        table=op.table,
        data=op.data,
        conflict_target=op.conflict_target,
        returning=op.returning,
    ),
}


async def _run_operation(conn, op: Operation, timeout: float) -> dict[str, Any]:
    sql, params = _BUILDERS[op.action](op)
    entry: dict[str, Any] = {}
    if op.returning:
        rows = await conn.fetch(sql, *params, timeout=timeout)
        entry["affected_rows"] = len(rows)
        entry["returning"] = [dict(row) for row in rows]
    else:
        status = await conn.execute(sql, *params, timeout=timeout)
        entry["affected_rows"] = parse_rows_affected(status)
    if op.alias:
        entry["alias"] = op.alias
    return entry


@router.post("/transaction")
async def transaction(
    body: TransactionRequest, caller: CallerDep, claims: ClaimsDep, request: Request
) -> dict:
    require_db_access(claims, caller, "write:database")
    settings = request.app.state.settings
    schema = resolve_schema(caller.tenant, body.schema_name)

    results: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        async with (
            request.app.state.db.acquire(schema=schema) as conn,
            conn.transaction(isolation=body.isolation_level),
        ):
            for op in body.operations:
                results.append(
                    await _run_operation(conn, op, settings.query_timeout_seconds)
                )
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc

    return {
        "transaction_id": new_id("txn"),
        "committed": True,
        "results": results,
        "execution_time_ms": round((time.perf_counter() - started) * 1000, 2),
    }
