"""Bases de datos del tenant (docs/freya-api-contract.md §4.4, §4.5).

Un tenant tiene siempre su base por defecto (su propio nombre); puede
crear bases con nombre adicional dentro de su namespace ("<tenant>_algo",
p.ej. "fortuna_staging") pero nunca una ajena. Cada base es una base
Postgres física real (pedido explícito del usuario: aislamiento real, no
un schema compartiendo servidor con los demás) -- las operaciones de
catálogo (listar/crear/borrar) corren contra la base ancla `postgres`,
nunca "desde dentro" de la base que se está creando o borrando.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import Conflict, require_permissions

from app.deps import CallerDep, ClaimsDep, require_db_access
from app.domain.pool import ANCHOR_DATABASE
from app.domain.tenant import quote_identifier, resolve_database
from app.infra.db import PG_ERRORS, translate_pg_error
from app.models.requests import DatabaseCreateRequest

router = APIRouter(tags=["databases"])


@router.get("/databases")
async def list_databases(
    caller: CallerDep, claims: ClaimsDep, request: Request
) -> list[dict]:
    require_db_access(claims, caller, "read:database")
    try:
        async with request.app.state.db.acquire(ANCHOR_DATABASE) as conn:
            rows = await conn.fetch(
                "SELECT datname FROM pg_database "
                "WHERE datname = $1 OR datname LIKE $2 "
                "ORDER BY datname",
                caller.tenant,
                f"{caller.tenant}_%",
            )
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc
    return [{"database": row["datname"]} for row in rows]


@router.post("/databases", status_code=201)
async def create_database(
    body: DatabaseCreateRequest, caller: CallerDep, claims: ClaimsDep, request: Request
) -> dict:
    require_db_access(claims, caller, "write:database")
    database = resolve_database(caller.tenant, body.database_name)
    try:
        async with request.app.state.db.acquire(ANCHOR_DATABASE) as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", database
            )
            if exists:
                raise Conflict(
                    f"La base '{database}' ya existe", details={"database": database}
                )
            # CREATE DATABASE no admite estar dentro de una transacción --
            # Postgres lo rechaza. conn.execute() suelto aquí es a
            # propósito, nunca conn.transaction().
            await conn.execute(f"CREATE DATABASE {quote_identifier(database)}")
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc
    return {"database": database}


@router.delete("/databases/{database_name}", status_code=204)
async def drop_database(
    database_name: str, caller: CallerDep, claims: ClaimsDep, request: Request
) -> None:
    """Borra una base entera, con todo su contenido -- pedido explícito
    del usuario: "el admin puede eliminar tenant cargándose todo lo que
    tiene ese tenant". resolve_database ya garantiza que `database_name`
    sea el propio tenant del llamante o uno de sus "<tenant>_algo" --
    nunca uno ajeno, y nunca "postgres"/"template0"/"template1".

    A diferencia de DROP SCHEMA, DROP DATABASE no tiene ni necesita
    CASCADE: borrar una base siempre se lleva todo su contenido. `WITH
    (FORCE)` (Postgres 13+) corta cualquier conexión colgada contra esa
    base antes de borrarla -- sin esto, una conexión abierta (aunque sea
    de otra petición en curso) haría fallar el DROP con "database is
    being accessed by other users".

    Hallazgo de seguridad (ronda anterior, al extender caller_context
    para aceptar JWT de usuario): este endpoint nunca tuvo NINGÚN chequeo
    de permiso -- antes sólo lo alcanzaba un token de servicio (ya de
    confianza alta), pero con usuarios aceptados también habría dejado a
    cualquier cuenta "user", sin ningún grant, borrar la base entera de
    su propio tenant. require_permissions (plano, no require_db_access a
    propósito) exige el flat "write:database" -- sólo admin o un
    servicio lo tienen; un grant de "database" por tenant (ver
    TENANT_GRANTABLE_PERMISSIONS) nunca alcanza para esto. Borrar un
    tenant entero sigue siendo sólo cosa del flujo orquestado de
    auth/app/domain/tenants.py:delete_tenant."""
    require_permissions(claims, "write:database")
    database = resolve_database(caller.tenant, database_name)
    try:
        async with request.app.state.db.acquire(ANCHOR_DATABASE) as conn:
            await conn.execute(
                f"DROP DATABASE IF EXISTS {quote_identifier(database)} WITH (FORCE)"
            )
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc
