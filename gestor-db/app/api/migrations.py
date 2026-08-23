"""POST /migrations — motor de migraciones versionadas (gdb-06)."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Request
from freya_common import require_permissions

from app.deps import CallerDep, ClaimsDep
from app.domain.migrations import apply_migrations
from app.domain.tenant import resolve_schema
from app.infra.db import translate_pg_error
from app.models.requests import MigrationsRequest

router = APIRouter(tags=["migrations"])


@router.post("/migrations")
async def migrate(
    body: MigrationsRequest, caller: CallerDep, claims: ClaimsDep, request: Request
) -> dict:
    require_permissions(claims, "write:database")
    schema = resolve_schema(caller.tenant, body.schema_name)
    migrations = [(item.filename, item.sql) for item in body.migrations]
    try:
        return await apply_migrations(
            request.app.state.db,
            schema=schema,
            service=caller.service,
            migrations=migrations,
        )
    except asyncpg.PostgresError as exc:
        raise translate_pg_error(exc) from exc
