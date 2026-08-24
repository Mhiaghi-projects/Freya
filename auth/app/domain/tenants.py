"""Tenants (proyectos) y accesos por proyecto.

Pedido explícito del usuario: la identidad de una cuenta vive en un solo
sitio (el tenant "freya", plano de control), pero qué proyectos puede ver
y con qué permisos se decide aparte, en user_tenant_grants -- tener un
tenant asignado no implica ningún permiso; cada servicio (storage,
monitoring) se concede por separado, por tenant.
"""

from __future__ import annotations

from typing import Any

from freya_common import (
    BadRequest,
    Conflict,
    NotFound,
    ServiceClient,
    gdb_mutate,
    gdb_query,
)

# Único home real de este registro y de los grants -- auth siempre opera
# aquí para estas dos tablas, sin importar qué tenant esté eligiendo ver
# quien llama (current_tenant() es del recurso que se está mirando, no de
# dónde vive la cuenta).
CONTROL_PLANE_TENANT = "freya"

# Únicos dos servicios que hoy se conceden por proyecto (pedido explícito
# del usuario). git/cicd/project-manager siguen siendo grants planos
# (SERVICE_GRANTS en app.domain.users), sin tenant.
TENANT_GRANTABLE_PERMISSIONS: dict[str, list[str]] = {
    "storage": ["read:storage", "write:storage"],
    "monitoring": ["read:monitoring", "write:monitoring"],
}

_GRANTABLE = {p for perms in TENANT_GRANTABLE_PERMISSIONS.values() for p in perms}


def _validate_tenant_permissions(permissions: list[str]) -> None:
    unknown = [p for p in permissions if p not in _GRANTABLE]
    if unknown:
        raise BadRequest(
            f"permiso(s) de proyecto no concedible(s): {unknown}",
            details={"grantable": sorted(_GRANTABLE)},
        )


async def create_tenant(
    client: ServiceClient, *, tenant_id: str, name: str, created_by: str | None
) -> dict[str, Any]:
    existing = await gdb_query(
        client,
        CONTROL_PLANE_TENANT,
        table="tenants",
        select=["id"],
        where={"id": tenant_id},
    )
    if existing:
        raise Conflict(f"el tenant '{tenant_id}' ya existe")
    await gdb_mutate(
        client,
        CONTROL_PLANE_TENANT,
        table="tenants",
        action="insert",
        data={"id": tenant_id, "name": name, "created_by": created_by},
    )
    return {"id": tenant_id, "name": name}


async def list_tenants(client: ServiceClient) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        CONTROL_PLANE_TENANT,
        table="tenants",
        select=["id", "name", "created_at", "created_by"],
    )


async def get_tenant(client: ServiceClient, tenant_id: str) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        CONTROL_PLANE_TENANT,
        table="tenants",
        select=["id", "name", "created_at", "created_by"],
        where={"id": tenant_id},
    )
    if not rows:
        raise NotFound(f"el tenant '{tenant_id}' no existe")
    return rows[0]


async def tenant_grants_of(client: ServiceClient, user_id: str) -> dict[str, list[str]]:
    """Mapa {tenant_id: [permisos]} de un usuario -- se embebe tal cual en
    el JWT al hacer login/refresh (app.domain.tokens.issue_user_token)."""
    rows = await gdb_query(
        client,
        CONTROL_PLANE_TENANT,
        table="user_tenant_grants",
        select=["tenant_id", "permissions"],
        where={"user_id": user_id},
    )
    return {row["tenant_id"]: row["permissions"] for row in rows}


async def set_tenant_grant(
    client: ServiceClient, *, user_id: str, tenant_id: str, permissions: list[str]
) -> None:
    """Reemplaza los permisos de (user_id, tenant_id). Una lista vacía
    equivale a quitar el acceso a ese proyecto -- borra la fila en vez de
    dejar un permissions=[] huérfano, así "tener el tenant asignado" sigue
    siendo exactamente "tener una fila aquí"."""
    _validate_tenant_permissions(permissions)
    await get_tenant(client, tenant_id)
    if not permissions:
        await gdb_mutate(
            client,
            CONTROL_PLANE_TENANT,
            table="user_tenant_grants",
            action="delete",
            where={"user_id": user_id, "tenant_id": tenant_id},
        )
        return
    existing = await gdb_query(
        client,
        CONTROL_PLANE_TENANT,
        table="user_tenant_grants",
        select=["user_id"],
        where={"user_id": user_id, "tenant_id": tenant_id},
    )
    action = "update" if existing else "insert"
    data = {"user_id": user_id, "tenant_id": tenant_id, "permissions": permissions}
    if action == "update":
        await gdb_mutate(
            client,
            CONTROL_PLANE_TENANT,
            table="user_tenant_grants",
            action="update",
            where={"user_id": user_id, "tenant_id": tenant_id},
            data={"permissions": permissions},
        )
    else:
        await gdb_mutate(
            client,
            CONTROL_PLANE_TENANT,
            table="user_tenant_grants",
            action="insert",
            data=data,
        )
