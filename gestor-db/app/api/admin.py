"""Aprovisionamiento y baja de tenants para gestor-db (mismo patrón que
storage/git/cicd/project-manager, ver sus respectivos app/api/admin.py):
sólo role: admin, no es un acceso por proyecto (TENANT_GRANTABLE_PERMISSIONS
de auth).

A diferencia de POST/DELETE /databases (pensados para que un proyecto
gestione sus propias bases "como un RDS", con sus propias reglas: crear
rechaza si ya existe, borrar es de una única base), estos dos endpoints
son la orquestación de plataforma que dispara auth/app/domain/tenants.py
al crear o eliminar un tenant entero -- provision es idempotente
(CREATE DATABASE si no existe, nunca 409) y la baja se lleva TODAS las
bases del tenant de un golpe, no sólo la principal (pedido explícito del
usuario: "cuando eliminas el tenant, debes eliminar todo eso")."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import Forbidden, require_permissions

from app.deps import ClaimsDep
from app.domain.migrations import ensure_database
from app.domain.pool import ANCHOR_DATABASE
from app.domain.tenant import quote_identifier, validate_tenant
from app.infra.db import PG_ERRORS, translate_pg_error

router = APIRouter(tags=["admin"])


def _require_admin(claims: dict) -> None:
    if claims.get("role") != "admin":
        raise Forbidden("Sólo un admin puede administrar tenants")


@router.post("/admin/tenants/{tenant}/provision", status_code=201)
async def provision(tenant: str, claims: ClaimsDep, request: Request) -> dict:
    _require_admin(claims)
    database = validate_tenant(tenant)
    try:
        await ensure_database(request.app.state.db, database)
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc
    return {"tenant": database}


@router.delete("/admin/tenants/{tenant}", status_code=204)
async def delete_all_databases(
    tenant: str, claims: ClaimsDep, request: Request
) -> None:
    """Borra la base por defecto del tenant y cualquier otra que haya
    creado dentro de su namespace (<tenant>_algo, p.ej. heracles_staging
    vía POST /api/database/databases) -- de lo contrario quedarían
    huérfanas al borrar el tenant entero. require_permissions plano, no
    require_db_access a propósito, igual que drop_database: un grant de
    "database" por tenant nunca alcanza para esto, sólo admin o el propio
    flujo orquestado de auth/app/domain/tenants.py:delete_tenant (que
    llama aquí con su token de servicio)."""
    require_permissions(claims, "write:database")
    tenant = validate_tenant(tenant)
    try:
        async with request.app.state.db.acquire(ANCHOR_DATABASE) as conn:
            rows = await conn.fetch(
                "SELECT datname FROM pg_database "
                "WHERE datname = $1 OR datname LIKE $2",
                tenant,
                f"{tenant}_%",
            )
            for row in rows:
                await conn.execute(
                    f"DROP DATABASE IF EXISTS "
                    f"{quote_identifier(row['datname'])} WITH (FORCE)"
                )
    except PG_ERRORS as exc:
        raise translate_pg_error(exc) from exc
