"""Milestones y progreso (ROADMAP.md pm-05: "calculado a partir de la
dificultad de sus tasks, no de su número")."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freya_common import NotFound, ServiceClient, gdb_mutate, gdb_query, new_id

_GDB_MAX_LIMIT = 200


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_milestone(
    client: ServiceClient,
    tenant: str,
    *,
    project_id: str,
    title: str,
    description: str,
    target_date: str | None,
) -> dict[str, Any]:
    milestone_id = new_id("mst")
    await gdb_mutate(
        client,
        tenant,
        table="pm_milestones",
        action="insert",
        data={
            "id": milestone_id,
            "project_id": project_id,
            "title": title,
            "description": description,
            "target_date": target_date,
        },
    )
    return {"milestone_id": milestone_id, "project_id": project_id, "title": title}


async def get_milestone(
    client: ServiceClient, tenant: str, *, milestone_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="pm_milestones",
        select=[
            "id",
            "project_id",
            "title",
            "description",
            "target_date",
            "created_at",
        ],
        where={"id": milestone_id, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if not rows:
        raise NotFound(
            f"El milestone '{milestone_id}' no existe",
            details={"milestone_id": milestone_id},
        )
    return rows[0]


async def list_milestones(
    client: ServiceClient, tenant: str, *, project_id: str
) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="pm_milestones",
        select=["id", "title", "target_date", "created_at"],
        where={"project_id": project_id, "deleted_at": {"is_null": True}},
        order_by=[{"field": "created_at", "direction": "asc"}],
        limit=200,
    )


async def milestone_progress(
    client: ServiceClient, tenant: str, *, milestone_id: str
) -> dict[str, Any]:
    milestone = await get_milestone(client, tenant, milestone_id=milestone_id)

    tasks: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await gdb_query(
            client,
            tenant,
            table="pm_tasks",
            select=["id", "difficulty", "status"],
            where={"milestone_id": milestone_id, "deleted_at": {"is_null": True}},
            limit=_GDB_MAX_LIMIT,
            offset=offset,
        )
        tasks.extend(page)
        if len(page) < _GDB_MAX_LIMIT:
            break
        offset += _GDB_MAX_LIMIT

    total_difficulty = sum(t["difficulty"] for t in tasks)
    done_difficulty = sum(t["difficulty"] for t in tasks if t["status"] == "done")
    percent = 0.0
    if total_difficulty:
        percent = round((done_difficulty / total_difficulty) * 100, 1)

    return {
        "milestone_id": milestone_id,
        "title": milestone["title"],
        "target_date": milestone["target_date"],
        "task_count": len(tasks),
        "tasks_done": sum(1 for t in tasks if t["status"] == "done"),
        "total_difficulty": total_difficulty,
        "done_difficulty": done_difficulty,
        "completion_percent": percent,
    }
