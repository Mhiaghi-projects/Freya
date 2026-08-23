"""Vínculo task <-> commit de git (docs/freya-api-contract.md §7.4).

Sólo registra el par: no valida contra el servicio git que el commit
exista de verdad (git no tiene hoy un "get commit by hash" propio, sólo
listados filtrables) -- queda como mejora futura, ver README.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freya_common import ServiceClient, gdb_mutate, gdb_query, new_id


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def link_commit(
    client: ServiceClient,
    tenant: str,
    *,
    task_id: str,
    repo_id: str,
    commit_hash: str,
) -> dict[str, Any]:
    link_id = new_id("lnk")
    await gdb_mutate(
        client,
        tenant,
        table="pm_task_commits",
        action="upsert",
        conflict_target=["task_id", "repo_id", "commit_hash"],
        data={
            "id": link_id,
            "task_id": task_id,
            "repo_id": repo_id,
            "commit_hash": commit_hash,
        },
    )
    return {
        "task_id": task_id,
        "repo_id": repo_id,
        "commit_hash": commit_hash,
        "linked_at": _now(),
    }


async def list_commits_for_task(
    client: ServiceClient, tenant: str, *, task_id: str
) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="pm_task_commits",
        select=["repo_id", "commit_hash", "linked_at"],
        where={"task_id": task_id},
        order_by=[{"field": "linked_at", "direction": "desc"}],
        limit=200,
    )
