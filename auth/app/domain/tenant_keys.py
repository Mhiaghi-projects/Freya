"""Credenciales de tenant "como las nubes" (pedido explícito del usuario):
un par key_id/api_secret por proyecto, generado desde el panel, para que
scripts, CI externo u otro backend llamen a Freya sin login de navegador.

Se canjea por un JWT de corta duración vía POST /api/v1/auth/token
(app.domain.tokens.issue_tenant_key_token) -- ese JWT trae exactamente la
misma forma que uno de usuario (`tenant_grants: {tenant: permissions}`,
`permissions` plano siempre vacío), así que storage/git/cicd/
project-manager/gestor-db lo aceptan sin ningún cambio: ya saben leer
tenant_grants para decidir acceso por proyecto (docs/DECISIONS.md).

Mismo patrón que app.domain.accounts (cuentas de servicio de la propia
malla): Argon2id sobre el secreto, sólo se guarda el hash. La diferencia es
el permiso concedible -- una cuenta de servicio recibe permisos planos de
la malla interna; una tenant_api_key sólo TENANT_GRANTABLE_PERMISSIONS,
igual que un grant humano por proyecto.
"""

from __future__ import annotations

import secrets
from typing import Any

from freya_common import (
    NotFound,
    ServiceClient,
    Unauthorized,
    gdb_mutate,
    gdb_query,
    new_id,
)

from app.domain.passwords import hash_secret, verify_secret
from app.domain.tenants import (
    CONTROL_PLANE_TENANT,
    get_tenant,
    validate_tenant_permissions,
)

# Sin 0/1/O/I: un key_id se transcribe a mano alguna vez (como un Access
# Key ID de AWS) y esos cuatro caracteres se confunden entre sí.
_KEY_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_KEY_ID_LENGTH = 16
_KEY_ID_PREFIX = "FRAK"


def _generate_key_id() -> str:
    return _KEY_ID_PREFIX + "".join(
        secrets.choice(_KEY_ID_ALPHABET) for _ in range(_KEY_ID_LENGTH)
    )


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)


async def create_tenant_api_key(
    client: ServiceClient,
    *,
    tenant_id: str,
    name: str,
    permissions: list[str],
    created_by: str | None,
) -> dict[str, Any]:
    """Devuelve el secreto EN CLARO -- única vez que se ve, ni el panel ni
    esta API lo vuelven a mostrar después. Sólo su hash queda guardado."""
    await get_tenant(client, tenant_id)  # 404 si el tenant no existe
    validate_tenant_permissions(permissions)
    row_id = new_id("tak")
    key_id = _generate_key_id()
    secret = _generate_secret()
    await gdb_mutate(
        client,
        CONTROL_PLANE_TENANT,
        table="tenant_api_keys",
        action="insert",
        data={
            "id": row_id,
            "tenant_id": tenant_id,
            "key_id": key_id,
            "secret_hash": hash_secret(secret),
            "name": name,
            "permissions": permissions,
            "created_by": created_by,
        },
    )
    return {
        "id": row_id,
        "tenant_id": tenant_id,
        "key_id": key_id,
        "api_secret": secret,
        "name": name,
        "permissions": permissions,
    }


async def list_tenant_api_keys(
    client: ServiceClient, tenant_id: str
) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        CONTROL_PLANE_TENANT,
        table="tenant_api_keys",
        select=["id", "key_id", "name", "permissions", "is_active", "created_at"],
        where={"tenant_id": tenant_id},
        order_by=[{"field": "created_at", "direction": "desc"}],
    )


async def revoke_tenant_api_key(
    client: ServiceClient, *, tenant_id: str, key_id: str
) -> None:
    rows = await gdb_query(
        client,
        CONTROL_PLANE_TENANT,
        table="tenant_api_keys",
        select=["id"],
        where={"tenant_id": tenant_id, "key_id": key_id},
        limit=1,
    )
    if not rows:
        raise NotFound(f"No existe la key '{key_id}' para el tenant '{tenant_id}'")
    await gdb_mutate(
        client,
        CONTROL_PLANE_TENANT,
        table="tenant_api_keys",
        action="delete",
        where={"id": rows[0]["id"]},
    )


async def authenticate_tenant_api_key(
    client: ServiceClient, *, key_id: str, api_secret: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        CONTROL_PLANE_TENANT,
        table="tenant_api_keys",
        select=["id", "tenant_id", "secret_hash", "permissions", "is_active"],
        where={"key_id": key_id},
    )
    if (
        not rows
        or not rows[0]["is_active"]
        or not verify_secret(api_secret, rows[0]["secret_hash"])
    ):
        raise Unauthorized("key_id o api_secret inválidos")
    return {
        "id": rows[0]["id"],
        "tenant_id": rows[0]["tenant_id"],
        "permissions": rows[0]["permissions"] or [],
    }
