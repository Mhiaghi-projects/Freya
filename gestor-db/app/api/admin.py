"""Aprovisionamiento y baja de tenants para gestor-db (mismo patrón que
storage/git/cicd/project-manager, ver sus respectivos app/api/admin.py):
sólo role: admin, no es un acceso por proyecto (TENANT_GRANTABLE_PERMISSIONS
de auth).

A diferencia de POST/DELETE /schemas (pensados para que un proyecto gestione
sus propios schemas "como un RDS", con sus propias reglas: crear rechaza si
ya existe, borrar es de un único schema), estos dos endpoints son la
orquestación de plataforma que dispara auth/app/domain/tenants.py al crear o
eliminar un tenant entero -- provision es idempotente (CREATE SCHEMA IF NOT
EXISTS, nunca 409) y la baja se lleva TODOS los schemas del tenant de un
golpe, no sólo el principal (pedido explícito del usuario: "cuando eliminas
el tenant, debes eliminar todo eso")."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import Forbidden, require_permissions

from app.deps import ClaimsDep
from app.domain.tenant import quote_identifier, validate_tenant
from app.infra.db import PG_ERRORS, translate_pg_error

router = APIRouter(tags=["admin"])


def _require_admin(claims: dict) -> None:
    if claims.get("role") != "admin":
        raise Forbidden("Sólo un admin puede administrar tenants")


@router.post("/admin/tenants/{tenant}/provision", status_code=201)
async def provision(tenant: str, claims: ClaimsDep, request: Request) -> dict:
    _require_admin(claims)
    schema = validate_tenant(tenant)
    try:
        async with request.app.state.db.acquire() as conn:
            await conn.execute(
                f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(schema)}"
            )
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc
    return {"tenant": schema}


@router.delete("/admin/tenants/{tenant}", status_code=204)
async def delete_all_schemas(tenant: str, claims: ClaimsDep, request: Request) -> None:
    """Borra el schema por defecto del tenant y cualquier otro que haya
    creado dentro de su namespace (<tenant>_algo, p.ej. heracles_staging vía
    POST /api/database/schemas) -- de lo contrario quedarían huérfanos al
    borrar el tenant entero, ya que DELETE /schemas/{schema_name} sólo se
    lleva un schema a la vez. require_permissions plano, no require_db_access
    a propósito, igual que drop_schema: un grant de "database" por tenant
    nunca alcanza para esto, sólo admin o el propio flujo orquestado de
    auth/app/domain/tenants.py:delete_tenant (que llama aquí con su token de
    servicio)."""
    require_permissions(claims, "write:database")
    tenant = validate_tenant(tenant)
    try:
        async with request.app.state.db.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name = $1 OR schema_name LIKE $2",
                tenant,
                f"{tenant}_%",
            )
            for row in rows:
                await conn.execute(
                    f"DROP SCHEMA IF EXISTS "
                    f"{quote_identifier(row['schema_name'])} CASCADE"
                )
            await conn.execute(
                "DELETE FROM public.freya_schema_migrations "
                "WHERE schema_name = $1 OR schema_name LIKE $2",
                tenant,
                f"{tenant}_%",
            )
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc
