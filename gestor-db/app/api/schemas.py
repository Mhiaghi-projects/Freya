"""Schemas del tenant (docs/freya-api-contract.md §4.4, §4.5).

Un tenant tiene siempre su schema por defecto (su propio nombre); puede
crear schemas con nombre adicionales dentro de su namespace
("<tenant>_algo", p.ej. "fortuna_staging") pero nunca uno ajeno.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import Conflict, require_permissions

from app.deps import CallerDep, ClaimsDep
from app.domain.tenant import quote_identifier, resolve_schema
from app.infra.db import PG_ERRORS, translate_pg_error
from app.models.requests import SchemaCreateRequest

router = APIRouter(tags=["schemas"])


@router.get("/schemas")
async def list_schemas(
    caller: CallerDep, claims: ClaimsDep, request: Request
) -> list[dict]:
    require_permissions(claims, "read:database")
    try:
        async with request.app.state.db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name = $1 OR schema_name LIKE $2 "
                "ORDER BY schema_name",
                caller.tenant,
                f"{caller.tenant}_%",
            )
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc
    return [{"schema": row["schema_name"]} for row in rows]


@router.post("/schemas", status_code=201)
async def create_schema(
    body: SchemaCreateRequest, caller: CallerDep, claims: ClaimsDep, request: Request
) -> dict:
    require_permissions(claims, "write:database")
    schema = resolve_schema(caller.tenant, body.schema_name)
    try:
        async with request.app.state.db.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1",
                schema,
            )
            if exists:
                raise Conflict(
                    f"El schema '{schema}' ya existe", details={"schema": schema}
                )
            await conn.execute(f"CREATE SCHEMA {quote_identifier(schema)}")
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc
    return {"schema": schema}
