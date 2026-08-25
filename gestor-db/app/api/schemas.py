"""Schemas del tenant (docs/freya-api-contract.md §4.4, §4.5).

Un tenant tiene siempre su schema por defecto (su propio nombre); puede
crear schemas con nombre adicionales dentro de su namespace
("<tenant>_algo", p.ej. "fortuna_staging") pero nunca uno ajeno.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import Conflict, require_permissions

from app.deps import CallerDep, ClaimsDep, require_db_access
from app.domain.tenant import quote_identifier, resolve_schema
from app.infra.db import PG_ERRORS, translate_pg_error
from app.models.requests import SchemaCreateRequest

router = APIRouter(tags=["schemas"])


@router.get("/schemas")
async def list_schemas(
    caller: CallerDep, claims: ClaimsDep, request: Request
) -> list[dict]:
    require_db_access(claims, caller, "read:database")
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
    require_db_access(claims, caller, "write:database")
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


@router.delete("/schemas/{schema_name}", status_code=204)
async def drop_schema(
    schema_name: str, caller: CallerDep, claims: ClaimsDep, request: Request
) -> None:
    """Borra un schema entero, con todo su contenido (DROP ... CASCADE) --
    pedido explícito del usuario: "el admin puede eliminar tenant
    cargándose todo lo que tiene ese tenant". resolve_schema ya garantiza
    que `schema_name` sea el propio tenant del llamante o uno de sus
    "<tenant>_algo" -- nunca uno ajeno, y nunca "public".

    También limpia sus filas en public.freya_schema_migrations (hallazgo
    en vivo: esa tabla vive en "public", DROP SCHEMA no la toca -- sin
    esto, recrear un tenant con el mismo id hace que
    MigrationRunner/provision_tenant se salten sus migraciones creyendo
    que ya están aplicadas, dejando el schema nuevo sin sus tablas).

    Hallazgo de seguridad (al extender caller_context para aceptar JWT de
    usuario, ver app/deps.py): este endpoint nunca tuvo NINGÚN chequeo de
    permiso -- antes sólo lo alcanzaba un token de servicio (ya de
    confianza alta), pero con usuarios aceptados también habría dejado a
    cualquier cuenta "user", sin ningún grant, borrar el schema entero de
    su propio tenant. require_permissions (plano, no require_db_access a
    propósito) exige el flat "write:database" -- sólo admin o un
    servicio lo tienen; un grant de "database" por tenant (nuevo, ver
    TENANT_GRANTABLE_PERMISSIONS) nunca alcanza para esto. Borrar un
    tenant entero sigue siendo sólo cosa del flujo orquestado de
    auth/app/domain/tenants.py:delete_tenant."""
    require_permissions(claims, "write:database")
    schema = resolve_schema(caller.tenant, schema_name)
    try:
        async with request.app.state.db.acquire() as conn, conn.transaction():
            await conn.execute(
                f"DROP SCHEMA IF EXISTS {quote_identifier(schema)} CASCADE"
            )
            await conn.execute(
                "DELETE FROM public.freya_schema_migrations WHERE schema_name = $1",
                schema,
            )
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc
