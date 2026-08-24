"""Páginas: CRUD básico, con propiedad por usuario."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freya_common import (
    Forbidden,
    NotFound,
    ServiceClient,
    gdb_mutate,
    gdb_query,
    new_id,
)

_PAGE_SELECT = [
    "id", "title", "parent_id", "owner_user_id", "created_at", "updated_at",
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_page(
    client: ServiceClient,
    tenant: str,
    *,
    title: str,
    parent_id: str | None,
    owner_user_id: str,
) -> dict[str, Any]:
    if parent_id is not None:
        await get_page(client, tenant, page_id=parent_id, owner_user_id=owner_user_id)

    page_id = new_id("pag")
    await gdb_mutate(
        client,
        tenant,
        table="athenea_pages",
        action="insert",
        data={
            "id": page_id,
            "title": title,
            "parent_id": parent_id,
            "owner_user_id": owner_user_id,
        },
    )
    return await get_page(client, tenant, page_id=page_id, owner_user_id=owner_user_id)


async def get_page(
    client: ServiceClient, tenant: str, *, page_id: str, owner_user_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="athenea_pages",
        select=_PAGE_SELECT,
        where={"id": page_id, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if not rows:
        raise NotFound(f"La página '{page_id}' no existe", details={"page_id": page_id})
    page = rows[0]
    if page["owner_user_id"] != owner_user_id:
        raise Forbidden("Esta página pertenece a otro usuario")
    return page


async def list_pages(
    client: ServiceClient, tenant: str, *, owner_user_id: str, limit: int = 200
) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="athenea_pages",
        select=_PAGE_SELECT,
        where={"owner_user_id": owner_user_id, "deleted_at": {"is_null": True}},
        order_by=[{"field": "created_at", "direction": "desc"}],
        limit=limit,
    )


async def delete_page(
    client: ServiceClient, tenant: str, *, page_id: str, owner_user_id: str
) -> None:
    await get_page(client, tenant, page_id=page_id, owner_user_id=owner_user_id)
    await gdb_mutate(
        client,
        tenant,
        table="athenea_pages",
        action="update",
        where={"id": page_id},
        data={"deleted_at": _now()},
    )
