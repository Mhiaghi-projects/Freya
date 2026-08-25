"""GET /tables — tablas y columnas de un schema (docs/freya-api-contract.md §4.6)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.deps import CallerDep, ClaimsDep, require_db_access
from app.domain.tenant import resolve_schema
from app.infra.db import PG_ERRORS, translate_pg_error

router = APIRouter(tags=["tables"])


@router.get("/tables")
async def list_tables(
    caller: CallerDep,
    claims: ClaimsDep,
    request: Request,
    schema: str | None = Query(default=None),
) -> list[dict]:
    require_db_access(claims, caller, "read:database")
    target = resolve_schema(caller.tenant, schema)

    try:
        async with request.app.state.db.acquire() as conn:
            tables = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = $1 AND table_type = 'BASE TABLE' "
                "ORDER BY table_name",
                target,
            )
            result = []
            for table in tables:
                columns = await conn.fetch(
                    "SELECT column_name, data_type, is_nullable FROM "
                    "information_schema.columns "
                    "WHERE table_schema = $1 AND table_name = $2 "
                    "ORDER BY ordinal_position",
                    target,
                    table["table_name"],
                )
                result.append(
                    {
                        "table": table["table_name"],
                        "columns": [
                            {
                                "name": column["column_name"],
                                "type": column["data_type"],
                                "nullable": column["is_nullable"] == "YES",
                            }
                            for column in columns
                        ],
                    }
                )
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc

    return result
