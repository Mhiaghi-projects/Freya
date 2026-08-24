"""Usuarios: alta y login por contraseña (docs/freya-api-contract.md §2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freya_common import (
    BadRequest,
    ServiceClient,
    Unauthorized,
    gdb_mutate,
    gdb_query,
    new_id,
)

from app.domain.passwords import hash_secret, verify_secret

# Sólo dos TIPOS de cuenta -- un role por servicio (git_user, storage_user,
# ...) no dejaba combinar accesos: alguien que necesitara git Y cicd no
# tenía ningún role válido (pedido explícito del usuario: "debe haber solo
# 2 tipos de usuarios... el segundo puede tener diferentes roles según los
# servicios que usará"). El "qué servicios" de una cuenta "user" vive
# aparte, en extra_permissions (users.extra_permissions, ver
# SERVICE_GRANTS) -- mismo patrón que ya usa service_accounts.permissions,
# una lista libre en vez de una enumeración cerrada de roles.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    # read:storage/write:storage NO está en la base de "user" a propósito
    # (pedido explícito del usuario, sobre un diseño anterior donde todo
    # "user" lo tenía automático): write:storage da acceso a cualquier
    # bucket que no sea "users" (docs/ARCHITECTURE.md §2.1) sin ninguna
    # noción de dueño -- ni siquiera el espacio personal debe quedar
    # accesible sin que un admin lo conceda explícitamente. Ahora es un
    # grant más, igual que git/cicd/monitoring (ver SERVICE_GRANTS).
    "user": ["read:self", "update:self"],
    "admin": [
        "read:self", "update:self", "admin:users",
        "read:database", "write:database",
        "read:storage", "write:storage",
        "read:git", "write:git", "admin:git",
        "read:cicd", "write:cicd",
        "read:monitoring", "write:monitoring",
        "read:project-manager", "write:project-manager",
    ],
}

# Menú de accesos por servicio que un admin puede conceder a una cuenta
# "user", combinables libremente (GET /admin/service-grants expone esto
# para que el panel construya la lista de checkboxes). admin:git queda
# fuera a propósito -- borrar repos no es un grant que quepa dar por
# servicio, es cosa de administración de verdad.
SERVICE_GRANTS: dict[str, list[str]] = {
    "git": ["read:git", "write:git"],
    "cicd": ["read:cicd", "write:cicd"],
    "monitoring": ["read:monitoring", "write:monitoring"],
    "project-manager": ["read:project-manager", "write:project-manager"],
    "storage": ["read:storage", "write:storage"],
}

_GRANTABLE_PERMISSIONS = {p for perms in SERVICE_GRANTS.values() for p in perms}

# Temas de interfaz que el panel ofrece (pedido explícito del usuario: cada
# cuenta elige el suyo -- admin puede tener un tema distinto al de un
# "user" cualquiera). "freya" es el tema original, sigue siendo el
# predeterminado.
THEMES = ["freya", "claro", "oscuro", "naturaleza", "ciudad", "tormenta"]


def permissions_for_role(role: str) -> list[str]:
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["user"])


def _validate_extra_permissions(extra_permissions: list[str]) -> None:
    unknown = [p for p in extra_permissions if p not in _GRANTABLE_PERMISSIONS]
    if unknown:
        raise BadRequest(
            f"permiso(s) no concedible(s): {unknown}",
            details={"grantable": sorted(_GRANTABLE_PERMISSIONS)},
        )


def full_permissions(role: str, extra_permissions: list[str]) -> list[str]:
    merged = dict.fromkeys(permissions_for_role(role))
    merged.update(dict.fromkeys(extra_permissions))
    return list(merged)


async def create_user(
    client: ServiceClient,
    tenant: str,
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str = "",
    role: str = "user",
    extra_permissions: list[str] | None = None,
    must_change_password: bool = False,
) -> dict[str, Any]:
    if role not in ROLE_PERMISSIONS:
        raise BadRequest(
            f"role desconocido: '{role}'",
            details={"known_roles": list(ROLE_PERMISSIONS)},
        )
    extra_permissions = extra_permissions or []
    _validate_extra_permissions(extra_permissions)
    user_id = new_id("usr")
    await gdb_mutate(
        client,
        tenant,
        table="users",
        action="insert",
        data={
            "id": user_id,
            "email": email,
            "password_hash": hash_secret(password),
            "first_name": first_name,
            "last_name": last_name,
            "role": role,
            "extra_permissions": extra_permissions,
            "must_change_password": must_change_password,
        },
    )
    return {"user_id": user_id, "email": email, "first_name": first_name, "role": role}


async def update_user_permissions(
    client: ServiceClient, tenant: str, *, user_id: str, extra_permissions: list[str]
) -> None:
    _validate_extra_permissions(extra_permissions)
    await gdb_mutate(
        client,
        tenant,
        table="users",
        action="update",
        where={"id": user_id},
        data={"extra_permissions": extra_permissions},
    )


async def authenticate_user(
    client: ServiceClient, tenant: str, *, email: str, password: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="users",
        select=[
            "id", "password_hash", "role", "active",
            "must_change_password", "extra_permissions",
        ],
        where={"email": email},
    )
    stored_hash = rows[0]["password_hash"] if rows else None
    password_ok = verify_secret(password, stored_hash)
    if not rows or not rows[0]["active"] or not password_ok:
        raise Unauthorized("email o contraseña inválidos")

    user_id = rows[0]["id"]
    role = rows[0]["role"]
    await gdb_mutate(
        client,
        tenant,
        table="users",
        action="update",
        where={"id": user_id},
        data={"last_login": _now_iso()},
    )
    return {
        "id": user_id,
        "role": role,
        "permissions": full_permissions(role, rows[0]["extra_permissions"]),
        "must_change_password": rows[0]["must_change_password"],
    }


async def change_password(
    client: ServiceClient,
    tenant: str,
    *,
    user_id: str,
    current_password: str,
    new_password: str,
) -> None:
    rows = await gdb_query(
        client,
        tenant,
        table="users",
        select=["password_hash"],
        where={"id": user_id},
    )
    if not rows or not verify_secret(current_password, rows[0]["password_hash"]):
        raise Unauthorized("contraseña actual inválida")

    await gdb_mutate(
        client,
        tenant,
        table="users",
        action="update",
        where={"id": user_id},
        data={
            "password_hash": hash_secret(new_password),
            "must_change_password": False,
        },
    )


async def admin_reset_password(
    client: ServiceClient, tenant: str, *, user_id: str, new_password: str
) -> None:
    await gdb_mutate(
        client,
        tenant,
        table="users",
        action="update",
        where={"id": user_id},
        data={
            "password_hash": hash_secret(new_password),
            "must_change_password": True,
        },
    )


async def delete_user(client: ServiceClient, tenant: str, *, user_id: str) -> None:
    await gdb_mutate(
        client, tenant, table="users", action="delete", where={"id": user_id}
    )


async def role_and_permissions_of(
    client: ServiceClient, tenant: str, user_id: str
) -> tuple[str, list[str]]:
    rows = await gdb_query(
        client,
        tenant,
        table="users",
        select=["role", "extra_permissions"],
        where={"id": user_id},
    )
    if not rows:
        raise Unauthorized("usuario desconocido")
    role = rows[0]["role"]
    return role, full_permissions(role, rows[0]["extra_permissions"])


_PROFILE_FIELDS = [
    "id", "email", "first_name", "last_name", "role", "extra_permissions", "created_at",
    "theme",
]


async def get_user(client: ServiceClient, tenant: str, user_id: str) -> dict[str, Any]:
    rows = await gdb_query(
        client, tenant, table="users", select=_PROFILE_FIELDS, where={"id": user_id}
    )
    if not rows:
        raise Unauthorized("usuario desconocido")
    return rows[0]


async def list_users(client: ServiceClient, tenant: str) -> list[dict[str, Any]]:
    return await gdb_query(client, tenant, table="users", select=_PROFILE_FIELDS)


async def update_theme(
    client: ServiceClient, tenant: str, *, user_id: str, theme: str
) -> None:
    if theme not in THEMES:
        raise BadRequest(
            f"tema desconocido: '{theme}'", details={"known_themes": THEMES}
        )
    await gdb_mutate(
        client,
        tenant,
        table="users",
        action="update",
        where={"id": user_id},
        data={"theme": theme},
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
