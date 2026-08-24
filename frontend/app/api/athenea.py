"""Vista de athenea: proxy delgado sobre athenea/app/api/pages.py.

Prueba de un tenant externo (docs/ARCHITECTURE.md §9) consumiendo Freya
sólo a través de este gateway -- ni athenea ni storage publican puerto al
host, así que esta ruta es, en la práctica, la única puerta de un cliente
externo hacia las páginas de Athenea (igual que app/api/storage.py lo es
para sus adjuntos)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from freya_common import ServiceClient
from pydantic import BaseModel, Field

from app.infra.gateway import client_dep

router = APIRouter(prefix="/api/athenea", tags=["athenea"])
AtheneaClient = Annotated[ServiceClient, Depends(client_dep("athenea"))]


class PageCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None


class BlockCreate(BaseModel):
    block_type: str
    content: str = ""


class AttachmentCreate(BaseModel):
    bucket: str = Field(min_length=1, max_length=100)
    object_key: str = Field(min_length=1, max_length=1024)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = "application/octet-stream"


@router.post("/pages", status_code=201)
async def create_page(body: PageCreate, client: AtheneaClient) -> dict:
    response = await client.post("/api/v1/pages", json=body.model_dump())
    return ServiceClient.data(response)


@router.get("/pages")
async def list_pages(client: AtheneaClient) -> list:
    return ServiceClient.data(await client.get("/api/v1/pages"))


@router.get("/pages/{page_id}")
async def get_page(page_id: str, client: AtheneaClient) -> dict:
    return ServiceClient.data(await client.get(f"/api/v1/pages/{page_id}"))


@router.delete("/pages/{page_id}", status_code=204)
async def delete_page(page_id: str, client: AtheneaClient) -> None:
    await client.delete(f"/api/v1/pages/{page_id}")


@router.post("/pages/{page_id}/blocks", status_code=201)
async def add_block(page_id: str, body: BlockCreate, client: AtheneaClient) -> dict:
    response = await client.post(
        f"/api/v1/pages/{page_id}/blocks", json=body.model_dump()
    )
    return ServiceClient.data(response)


@router.get("/pages/{page_id}/blocks")
async def list_blocks(page_id: str, client: AtheneaClient) -> list:
    return ServiceClient.data(await client.get(f"/api/v1/pages/{page_id}/blocks"))


@router.post("/pages/{page_id}/attachments", status_code=201)
async def add_attachment(
    page_id: str, body: AttachmentCreate, client: AtheneaClient
) -> dict:
    response = await client.post(
        f"/api/v1/pages/{page_id}/attachments", json=body.model_dump()
    )
    return ServiceClient.data(response)


@router.get("/pages/{page_id}/attachments")
async def list_attachments(page_id: str, client: AtheneaClient) -> list:
    return ServiceClient.data(await client.get(f"/api/v1/pages/{page_id}/attachments"))
