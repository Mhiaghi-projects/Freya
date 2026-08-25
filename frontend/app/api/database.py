"""Vista de database (docs/DECISIONS.md, "gestor-db como un RDS"): proxy
delgado sobre gestor-db/app/api/{query,mutate,tables,databases}.py. Sólo
expone lectura/escritura de filas y creación/listado de bases -- nunca
DROP DATABASE ni /migrations (DDL crudo), que gestor-db exige de forma
deliberada como flat/servicio-only (ver gestor-db/app/deps.py)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from freya_common import ServiceClient
from pydantic import BaseModel, ConfigDict, Field

from app.infra.gateway import client_dep

router = APIRouter(prefix="/api/database", tags=["database"])
DatabaseClient = Annotated[ServiceClient, Depends(client_dep("gestor-db"))]


def _tenant(project: str | None) -> str:
    return project or "freya"


class OrderBy(BaseModel):
    column: str
    direction: Literal["asc", "desc"] = "asc"


class QueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    database_name: str | None = Field(default=None, alias="database")
    table: str
    select: list[str] | None = None
    where: dict[str, Any] | None = None
    order_by: list[OrderBy] | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class MutateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    database_name: str | None = Field(default=None, alias="database")
    table: str
    action: Literal["insert", "update", "delete", "upsert"]
    where: dict[str, Any] | None = None
    data: dict[str, Any] | list[dict[str, Any]] | None = None
    returning: list[str] | None = None
    conflict_target: list[str] | None = None


class DatabaseCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    database_name: str = Field(alias="database")


@router.get("/databases")
async def list_databases(client: DatabaseClient, project: str | None = None) -> list:
    return ServiceClient.data(
        await client.get("/databases", tenant=_tenant(project))
    )


@router.post("/databases", status_code=201)
async def create_database(
    body: DatabaseCreateRequest, client: DatabaseClient, project: str | None = None
) -> dict:
    return ServiceClient.data(
        await client.post(
            "/databases",
            json=body.model_dump(by_alias=True),
            tenant=_tenant(project),
        )
    )


@router.get("/tables")
async def list_tables(
    client: DatabaseClient,
    database: str | None = Query(default=None),
    project: str | None = None,
) -> list:
    params = {"database": database} if database else {}
    return ServiceClient.data(
        await client.get("/tables", params=params, tenant=_tenant(project))
    )


@router.post("/query")
async def query(
    body: QueryRequest, client: DatabaseClient, project: str | None = None
) -> dict:
    return ServiceClient.data(
        await client.post(
            "/query",
            json=body.model_dump(by_alias=True, exclude_none=True),
            tenant=_tenant(project),
        )
    )


@router.post("/mutate")
async def mutate(
    body: MutateRequest, client: DatabaseClient, project: str | None = None
) -> dict:
    return ServiceClient.data(
        await client.post(
            "/mutate",
            json=body.model_dump(by_alias=True, exclude_none=True),
            tenant=_tenant(project),
        )
    )
