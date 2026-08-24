"""Páginas, bloques y adjuntos (docs/ARCHITECTURE.md §9: tenant externo)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant

from app.deps import UserDep
from app.domain.attachments import list_attachments, record_attachment
from app.domain.blocks import add_block, list_blocks
from app.domain.pages import create_page, delete_page, get_page, list_pages
from app.models.requests import AttachmentCreate, BlockCreate, PageCreate

router = APIRouter(tags=["pages"])


@router.post("/pages", status_code=201)
async def create(body: PageCreate, claims: UserDep, request: Request) -> dict:
    return await create_page(
        request.app.state.gestor_db,
        current_tenant(),
        title=body.title,
        parent_id=body.parent_id,
        owner_user_id=claims["sub"],
    )


@router.get("/pages")
async def list_all(claims: UserDep, request: Request) -> list:
    return await list_pages(
        request.app.state.gestor_db, current_tenant(), owner_user_id=claims["sub"]
    )


@router.get("/pages/{page_id}")
async def get(page_id: str, claims: UserDep, request: Request) -> dict:
    return await get_page(
        request.app.state.gestor_db,
        current_tenant(),
        page_id=page_id,
        owner_user_id=claims["sub"],
    )


@router.delete("/pages/{page_id}", status_code=204)
async def delete(page_id: str, claims: UserDep, request: Request) -> None:
    await delete_page(
        request.app.state.gestor_db,
        current_tenant(),
        page_id=page_id,
        owner_user_id=claims["sub"],
    )


@router.post("/pages/{page_id}/blocks", status_code=201)
async def add(
    page_id: str, body: BlockCreate, claims: UserDep, request: Request
) -> dict:
    return await add_block(
        request.app.state.gestor_db,
        current_tenant(),
        page_id=page_id,
        owner_user_id=claims["sub"],
        block_type=body.block_type,
        content=body.content,
    )


@router.get("/pages/{page_id}/blocks")
async def list_page_blocks(page_id: str, claims: UserDep, request: Request) -> list:
    return await list_blocks(
        request.app.state.gestor_db,
        current_tenant(),
        page_id=page_id,
        owner_user_id=claims["sub"],
    )


@router.post("/pages/{page_id}/attachments", status_code=201)
async def add_attachment(
    page_id: str, body: AttachmentCreate, claims: UserDep, request: Request
) -> dict:
    """Registra el metadato de un objeto que el cliente ya subió a storage a
    través de POST /api/storage/{bucket}/{key} en frontend -- este servicio
    nunca sube ni descarga bytes."""
    return await record_attachment(
        request.app.state.gestor_db,
        current_tenant(),
        page_id=page_id,
        owner_user_id=claims["sub"],
        bucket=body.bucket,
        object_key=body.object_key,
        filename=body.filename,
        content_type=body.content_type,
    )


@router.get("/pages/{page_id}/attachments")
async def list_page_attachments(
    page_id: str, claims: UserDep, request: Request
) -> list:
    return await list_attachments(
        request.app.state.gestor_db,
        current_tenant(),
        page_id=page_id,
        owner_user_id=claims["sub"],
    )
