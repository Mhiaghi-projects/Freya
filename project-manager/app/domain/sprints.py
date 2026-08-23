"""Sprints (docs/freya-api-contract.md §7.6). Métricas en vivo a partir de
story_points; sin snapshot diario persistido de burndown -- eso pide un job
programado que todavía no existe (§13, futura "automation")."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freya_common import (
    NotFound,
    ServiceClient,
    UnprocessableEntity,
    gdb_mutate,
    gdb_query,
    new_id,
)

from app.domain.tasks import get_task

STATUSES = {"planned", "active", "completed"}
_GDB_MAX_LIMIT = 200


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_sprint(
    client: ServiceClient,
    tenant: str,
    *,
    project_id: str,
    name: str,
    goal: str,
    start_date: str | None,
    end_date: str | None,
    task_ids: list[str],
) -> dict[str, Any]:
    sprint_id = new_id("spr")
    await gdb_mutate(
        client,
        tenant,
        table="pm_sprints",
        action="insert",
        data={
            "id": sprint_id,
            "project_id": project_id,
            "name": name,
            "goal": goal,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    for task_id in task_ids:
        # A diferencia de tasks.create_task con depends_on, esto no
        # comprobaba que task_id existiera de verdad -- un id inválido o
        # de otro tenant hacía un UPDATE de cero filas sin avisar: el
        # caller creía que la task se había añadido al sprint y no era
        # cierto.
        await get_task(client, tenant, task_id=task_id)
        await gdb_mutate(
            client,
            tenant,
            table="pm_tasks",
            action="update",
            where={"id": task_id},
            data={"sprint_id": sprint_id},
        )
    return {"sprint_id": sprint_id, "project_id": project_id, "name": name}


async def get_sprint(
    client: ServiceClient,
    tenant: str,
    *,
    sprint_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="pm_sprints",
        select=["id", "project_id", "name", "goal", "status", "start_date", "end_date"],
        where={"id": sprint_id, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if not rows:
        raise NotFound(
            f"El sprint '{sprint_id}' no existe", details={"sprint_id": sprint_id}
        )
    sprint = rows[0]
    if project_id is not None and sprint["project_id"] != project_id:
        # GET/PUT /projects/{project_id}/sprints/{sprint_id} traen
        # project_id en la propia URL pero antes nunca se comprobaba que el
        # sprint encontrado por sprint_id perteneciera de verdad a ese
        # project_id -- cualquier project_id "funcionaba" mientras
        # sprint_id existiera en el tenant. No es una fuga entre tenants,
        # pero rompe el contrato de recurso anidado que la URL promete.
        raise NotFound(
            f"El sprint '{sprint_id}' no existe en el proyecto '{project_id}'",
            details={"sprint_id": sprint_id, "project_id": project_id},
        )
    return sprint


async def list_sprints(
    client: ServiceClient, tenant: str, *, project_id: str, status: str | None
) -> list[dict[str, Any]]:
    where: dict[str, Any] = {"project_id": project_id, "deleted_at": {"is_null": True}}
    if status:
        where["status"] = status
    return await gdb_query(
        client,
        tenant,
        table="pm_sprints",
        select=["id", "name", "status", "start_date", "end_date"],
        where=where,
        order_by=[{"field": "start_date", "direction": "desc"}],
        limit=200,
    )


async def update_sprint(
    client: ServiceClient,
    tenant: str,
    *,
    sprint_id: str,
    project_id: str,
    status: str | None,
) -> dict[str, Any]:
    await get_sprint(client, tenant, sprint_id=sprint_id, project_id=project_id)
    if status is not None:
        if status not in STATUSES:
            # 422, no 409: es una comprobación de pertenencia a un enum
            # (validate_priority/validate_difficulty/validate_story_points
            # hacen lo mismo en este servicio), no un conflicto de estado
            # -- docs/CONVENTIONS.md reserva 409 para eso.
            raise UnprocessableEntity(
                f"status debe ser uno de {sorted(STATUSES)}", details={"status": status}
            )
        await gdb_mutate(
            client,
            tenant,
            table="pm_sprints",
            action="update",
            where={"id": sprint_id},
            data={"status": status},
        )
    return await get_sprint(client, tenant, sprint_id=sprint_id, project_id=project_id)


async def sprint_metrics(
    client: ServiceClient, tenant: str, *, sprint_id: str, project_id: str
) -> dict[str, Any]:
    sprint = await get_sprint(
        client, tenant, sprint_id=sprint_id, project_id=project_id
    )

    tasks: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await gdb_query(
            client,
            tenant,
            table="pm_tasks",
            select=["id", "story_points", "status"],
            where={"sprint_id": sprint_id, "deleted_at": {"is_null": True}},
            limit=_GDB_MAX_LIMIT,
            offset=offset,
        )
        tasks.extend(page)
        if len(page) < _GDB_MAX_LIMIT:
            break
        offset += _GDB_MAX_LIMIT

    total_points = sum(t["story_points"] or 0 for t in tasks)
    done_points = sum(t["story_points"] or 0 for t in tasks if t["status"] == "done")
    percent = round((done_points / total_points) * 100, 1) if total_points else 0.0

    days_remaining = None
    if sprint["end_date"]:
        end = datetime.fromisoformat(str(sprint["end_date"])).replace(tzinfo=UTC)
        days_remaining = max((end - datetime.now(UTC)).days, 0)

    return {
        "sprint_id": sprint_id,
        "name": sprint["name"],
        "goal": sprint["goal"],
        "status": sprint["status"],
        "start_date": sprint["start_date"],
        "end_date": sprint["end_date"],
        "metrics": {
            "total_story_points": total_points,
            "completed_story_points": done_points,
            "completion_percent": percent,
            "tasks_total": len(tasks),
            "tasks_done": sum(1 for t in tasks if t["status"] == "done"),
            "days_remaining": days_remaining,
        },
    }
