"""Cuentas de servicio: alta y verificación (docs/freya-api-contract.md §15)."""

from __future__ import annotations

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


async def create_service_account(
    client: ServiceClient,
    tenant: str,
    *,
    service: str,
    api_secret: str,
    permissions: list[str],
) -> str:
    account_id = new_id("sva")
    await gdb_mutate(
        client,
        tenant,
        table="service_accounts",
        action="insert",
        data={
            "id": account_id,
            "service": service,
            "api_secret_hash": hash_secret(api_secret),
            "permissions": permissions,
        },
    )
    return account_id


async def update_service_account_permissions(
    client: ServiceClient, tenant: str, *, service: str, permissions: list[str]
) -> None:
    """Reemplaza la lista completa de permisos de una cuenta ya existente
    (nunca la añade a lo que hubiera antes: estado deseado, no incremental
    -- evita que dos llamadas con distinta idea de lo que hace falta dejen
    la cuenta en un estado que nadie pidió explícitamente)."""
    rows = await gdb_query(
        client,
        tenant,
        table="service_accounts",
        select=["id"],
        where={"service": service},
        limit=1,
    )
    if not rows:
        raise NotFound(f"No existe cuenta de servicio para '{service}'")
    await gdb_mutate(
        client,
        tenant,
        table="service_accounts",
        action="update",
        where={"id": rows[0]["id"]},
        data={"permissions": permissions},
    )


async def authenticate_service_account(
    client: ServiceClient, tenant: str, *, service: str, api_secret: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="service_accounts",
        select=["id", "api_secret_hash", "permissions", "is_active"],
        where={"service": service},
    )
    if (
        not rows
        or not rows[0]["is_active"]
        or not verify_secret(api_secret, rows[0]["api_secret_hash"])
    ):
        raise Unauthorized("service o api_secret inválidos")

    return {"id": rows[0]["id"], "permissions": rows[0]["permissions"] or []}
