"""Adjuntos: sólo el metadato que apunta a un objeto ya subido a storage por
el cliente a través del gateway de frontend (/api/storage) -- este servicio
nunca habla con storage directamente (docs/ARCHITECTURE.md §8)."""

from __future__ import annotations

from typing import Any

from freya_common import ServiceClient, gdb_mutate, gdb_query, new_id

from app.domain.pages import get_page

_ATTACHMENT_SELECT = [
    "id", "page_id", "bucket", "object_key", "filename", "content_type",
    "uploaded_by", "created_at",
]


async def record_attachment(
    client: ServiceClient,
    tenant: str,
    *,
    page_id: str,
    owner_user_id: str,
    bucket: str,
    object_key: str,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    await get_page(client, tenant, page_id=page_id, owner_user_id=owner_user_id)

    attachment_id = new_id("att")
    await gdb_mutate(
        client,
        tenant,
        table="athenea_attachments",
        action="insert",
        data={
            "id": attachment_id,
            "page_id": page_id,
            "bucket": bucket,
            "object_key": object_key,
            "filename": filename,
            "content_type": content_type,
            "uploaded_by": owner_user_id,
        },
    )
    rows = await gdb_query(
        client,
        tenant,
        table="athenea_attachments",
        select=_ATTACHMENT_SELECT,
        where={"id": attachment_id},
        limit=1,
    )
    return rows[0]


async def list_attachments(
    client: ServiceClient, tenant: str, *, page_id: str, owner_user_id: str
) -> list[dict[str, Any]]:
    await get_page(client, tenant, page_id=page_id, owner_user_id=owner_user_id)
    return await gdb_query(
        client,
        tenant,
        table="athenea_attachments",
        select=_ATTACHMENT_SELECT,
        where={"page_id": page_id},
        order_by=[{"field": "created_at", "direction": "asc"}],
        limit=200,
    )
