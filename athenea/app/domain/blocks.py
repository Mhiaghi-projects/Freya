"""Bloques de contenido dentro de una página."""

from __future__ import annotations

from typing import Any

from freya_common import (
    ServiceClient,
    UnprocessableEntity,
    gdb_mutate,
    gdb_query,
    new_id,
)

from app.domain.pages import get_page

_BLOCK_TYPES = {"text", "heading", "todo"}
_BLOCK_SELECT = ["id", "page_id", "block_type", "content", "position", "created_at"]


def validate_block_type(block_type: str) -> None:
    if block_type not in _BLOCK_TYPES:
        raise UnprocessableEntity(
            f"block_type debe ser uno de {sorted(_BLOCK_TYPES)}",
            details={"block_type": block_type},
        )


async def _next_position(client: ServiceClient, tenant: str, *, page_id: str) -> int:
    rows = await gdb_query(
        client,
        tenant,
        table="athenea_blocks",
        select=["position"],
        where={"page_id": page_id},
        order_by=[{"field": "position", "direction": "desc"}],
        limit=1,
    )
    return (rows[0]["position"] + 1) if rows else 0


async def add_block(
    client: ServiceClient,
    tenant: str,
    *,
    page_id: str,
    owner_user_id: str,
    block_type: str,
    content: str,
) -> dict[str, Any]:
    validate_block_type(block_type)
    await get_page(client, tenant, page_id=page_id, owner_user_id=owner_user_id)

    block_id = new_id("blk")
    position = await _next_position(client, tenant, page_id=page_id)
    await gdb_mutate(
        client,
        tenant,
        table="athenea_blocks",
        action="insert",
        data={
            "id": block_id,
            "page_id": page_id,
            "block_type": block_type,
            "content": content,
            "position": position,
        },
    )
    rows = await gdb_query(
        client,
        tenant,
        table="athenea_blocks",
        select=_BLOCK_SELECT,
        where={"id": block_id},
        limit=1,
    )
    return rows[0]


async def list_blocks(
    client: ServiceClient, tenant: str, *, page_id: str, owner_user_id: str
) -> list[dict[str, Any]]:
    await get_page(client, tenant, page_id=page_id, owner_user_id=owner_user_id)
    return await gdb_query(
        client,
        tenant,
        table="athenea_blocks",
        select=_BLOCK_SELECT,
        where={"page_id": page_id},
        order_by=[{"field": "position", "direction": "asc"}],
        limit=200,
    )
