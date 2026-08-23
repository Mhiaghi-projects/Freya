"""Proyectos (docs/freya-api-contract.md §7.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freya_common import (
    Conflict,
    NotFound,
    ServiceClient,
    UnprocessableEntity,
    gdb_mutate,
    gdb_query,
    new_id,
)

PROJECT_TYPES = {"programming", "electronics", "general"}

# "Columnas definibles por proyecto" (ROADMAP.md pm-04): esto es la semilla
# por defecto, no un enum fijo -- create_column/delete_column pueden
# cambiarlas por proyecto. Coincide con los 5 status de §7.2/§7.5.
DEFAULT_COLUMNS = [
    ("backlog", "Backlog"),
    ("todo", "To Do"),
    ("in_progress", "In Progress"),
    ("testing", "Testing"),
    ("done", "Done"),
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def validate_project_rules(
    *, project_type: str, ci_cd_enabled: bool, linked_git_repo: str | None
) -> None:
    """Reglas de §7.1 que no necesitan consultar la base."""
    if project_type not in PROJECT_TYPES:
        raise UnprocessableEntity(
            f"project_type debe ser uno de {sorted(PROJECT_TYPES)}",
            details={"project_type": project_type},
        )
    if ci_cd_enabled and project_type != "programming":
        raise UnprocessableEntity(
            "ci_cd_enabled sólo es válido con project_type: programming",
            details={"project_type": project_type},
        )
    if linked_git_repo and project_type == "general":
        raise UnprocessableEntity(
            "linked_git_repo no es válido con project_type: general",
            details={"project_type": project_type},
        )


async def create_project(
    client: ServiceClient,
    tenant: str,
    *,
    project_name: str,
    description: str,
    project_type: str,
    visibility: str,
    difficulty: int | None,
    linked_git_repo: str | None,
    ci_cd_enabled: bool,
    team_members: list[str],
) -> dict[str, Any]:
    validate_project_rules(
        project_type=project_type,
        ci_cd_enabled=ci_cd_enabled,
        linked_git_repo=linked_git_repo,
    )

    existing = await gdb_query(
        client,
        tenant,
        table="pm_projects",
        select=["id"],
        where={"project_name": project_name, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if existing:
        raise Conflict(
            f"El proyecto '{project_name}' ya existe",
            details={"project_name": project_name},
        )

    project_id = new_id("prj")
    await gdb_mutate(
        client,
        tenant,
        table="pm_projects",
        action="insert",
        data={
            "id": project_id,
            "project_name": project_name,
            "description": description,
            "project_type": project_type,
            "visibility": visibility,
            "difficulty": difficulty,
            "linked_git_repo": linked_git_repo,
            "ci_cd_enabled": ci_cd_enabled,
            "team_members": team_members,
        },
    )

    for position, (key, label) in enumerate(DEFAULT_COLUMNS):
        await gdb_mutate(
            client,
            tenant,
            table="pm_board_columns",
            action="insert",
            data={
                "id": new_id("col"),
                "project_id": project_id,
                "key": key,
                "label": label,
                "position": position,
            },
        )

    return {
        "project_id": project_id,
        "project_name": project_name,
        "project_type": project_type,
        "git_repo": linked_git_repo,
        "ci_cd_enabled": ci_cd_enabled,
        "created_at": _now(),
    }


async def get_project(
    client: ServiceClient, tenant: str, *, project_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="pm_projects",
        select=[
            "id",
            "project_name",
            "description",
            "project_type",
            "visibility",
            "difficulty",
            "linked_git_repo",
            "ci_cd_enabled",
            "team_members",
            "created_at",
        ],
        where={"id": project_id, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if not rows:
        raise NotFound(
            f"El proyecto '{project_id}' no existe", details={"project_id": project_id}
        )
    return rows[0]


async def list_projects(client: ServiceClient, tenant: str) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="pm_projects",
        select=["id", "project_name", "project_type", "visibility", "created_at"],
        where={"deleted_at": {"is_null": True}},
        order_by=[{"field": "project_name", "direction": "asc"}],
        limit=200,
    )


async def delete_project(
    client: ServiceClient, tenant: str, *, project_id: str
) -> None:
    await get_project(client, tenant, project_id=project_id)
    await gdb_mutate(
        client,
        tenant,
        table="pm_projects",
        action="update",
        where={"id": project_id},
        data={"deleted_at": _now()},
    )


async def list_columns(
    client: ServiceClient, tenant: str, *, project_id: str
) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="pm_board_columns",
        select=["id", "key", "label", "position", "wip_limit"],
        where={"project_id": project_id},
        order_by=[{"field": "position", "direction": "asc"}],
        limit=50,
    )
