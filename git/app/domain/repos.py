"""Catálogo de repositorios (docs/freya-api-contract.md §6.1, §6.4)."""

from __future__ import annotations

import re
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

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,99}$")


def validate_repo_name(repo_name: str) -> None:
    if not _NAME_RE.match(repo_name):
        raise UnprocessableEntity(
            f"'{repo_name}' no es un nombre de repositorio válido",
            details={"pattern": _NAME_RE.pattern},
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_repo(
    client: ServiceClient,
    tenant: str,
    *,
    repo_name: str,
    description: str,
    default_branch: str,
    visibility: str,
    sensitive: bool,
    github_mirror_url: str | None,
    github_sync_enabled: bool,
    secret_validation_enabled: bool,
) -> dict[str, Any]:
    existing = await gdb_query(
        client,
        tenant,
        table="git_repositories",
        select=["id"],
        where={"repo_name": repo_name, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if existing:
        raise Conflict(
            f"El repositorio '{repo_name}' ya existe", details={"repo_name": repo_name}
        )

    repo_id = new_id("repo")
    await gdb_mutate(
        client,
        tenant,
        table="git_repositories",
        action="insert",
        data={
            "id": repo_id,
            "repo_name": repo_name,
            "description": description,
            "default_branch": default_branch,
            "visibility": visibility,
            "sensitive": sensitive,
            "github_mirror_url": github_mirror_url,
            "github_sync_enabled": github_sync_enabled,
            "secret_validation_enabled": secret_validation_enabled,
        },
    )
    return {
        "repo_id": repo_id,
        "repo_name": repo_name,
        "tenant_id": tenant,
        "default_branch": default_branch,
        "visibility": visibility,
        "created_at": _now(),
    }


async def get_repo(
    client: ServiceClient, tenant: str, *, repo_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="git_repositories",
        select=[
            "id",
            "repo_name",
            "description",
            "default_branch",
            "visibility",
            "sensitive",
            "github_mirror_url",
            "github_sync_enabled",
            "secret_validation_enabled",
            "created_at",
        ],
        where={"id": repo_id, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if not rows:
        raise NotFound(
            f"El repositorio '{repo_id}' no existe", details={"repo_id": repo_id}
        )
    return rows[0]


async def get_repo_by_name(
    client: ServiceClient, tenant: str, *, repo_name: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="git_repositories",
        select=["id", "repo_name", "default_branch", "sensitive"],
        where={"repo_name": repo_name, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if not rows:
        raise NotFound(
            f"El repositorio '{repo_name}' no existe", details={"repo_name": repo_name}
        )
    return rows[0]


async def list_repos(client: ServiceClient, tenant: str) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="git_repositories",
        select=["id", "repo_name", "visibility", "default_branch", "created_at"],
        where={"deleted_at": {"is_null": True}},
        order_by=[{"field": "repo_name", "direction": "asc"}],
        limit=200,
    )


async def delete_repo(client: ServiceClient, tenant: str, *, repo_id: str) -> None:
    await get_repo(client, tenant, repo_id=repo_id)
    await gdb_mutate(
        client,
        tenant,
        table="git_repositories",
        action="update",
        where={"id": repo_id},
        data={"deleted_at": _now()},
    )
