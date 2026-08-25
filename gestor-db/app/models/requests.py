"""Esquemas pydantic de entrada de gestor-db (docs/freya-api-contract.md §4)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderBy(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class QueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Opcional a propósito (resolve_schema): sin "schema" en el cuerpo, se
    # usa el propio tenant del llamante -- el caso normal para un proyecto
    # que consulta sus propias tablas "como un RDS" (gestor-db/app/deps.py).
    schema_name: str | None = Field(default=None, alias="schema")
    table: str
    select: list[str] | None = None
    where: dict[str, Any] | None = None
    order_by: list[OrderBy] | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class MutateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str | None = Field(default=None, alias="schema")
    table: str
    action: Literal["insert", "update", "delete", "upsert"]
    where: dict[str, Any] | None = None
    data: dict[str, Any] | list[dict[str, Any]] | None = None
    returning: list[str] | None = None
    conflict_target: list[str] | None = None


class Operation(BaseModel):
    action: Literal["insert", "update", "delete", "upsert"]
    table: str
    where: dict[str, Any] | None = None
    data: dict[str, Any] | list[dict[str, Any]] | None = None
    returning: list[str] | None = None
    conflict_target: list[str] | None = None
    alias: str | None = None


class TransactionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str | None = Field(default=None, alias="schema")
    operations: list[Operation] = Field(min_length=1)
    isolation_level: Literal["read_committed", "repeatable_read", "serializable"] = (
        "read_committed"
    )


class SchemaCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")


class MigrationItem(BaseModel):
    filename: str = Field(min_length=1)
    sql: str = Field(min_length=1)


class MigrationsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")
    migrations: list[MigrationItem] = Field(min_length=1)
