"""Tasks: CRUD, dependencias, transición de estado, esfuerzo
(docs/freya-api-contract.md §7.2, §7.3; ROADMAP.md pm-03, pm-06)."""

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

from app.domain.projects import list_columns

PRIORITIES = {"low", "medium", "high", "critical"}
STORY_POINTS = {1, 2, 3, 5, 8, 13, 21}
DONE_STATUS = "done"
# "una task bloqueada no puede pasar a en curso" (ROADMAP.md pm-03): mover
# a backlog/todo siempre vale (es donde vive mientras está bloqueada);
# cualquier otra columna exige que las dependencias ya estén en 'done'.
_UNBLOCKED_STATUSES = {"backlog", "todo"}

# Estimación por defecto cuando no se da estimated_hours explícito: escala
# que dobla por nivel, igual de arbitraria (y suficiente) que los puntos de
# historia de Fibonacci del contrato -- aquí en horas porque es lo que
# ROADMAP.md pm-06 pide comparar contra el tiempo real.
HOURS_BY_DIFFICULTY = {1: 2, 2: 4, 3: 8, 4: 16, 5: 32}

_TASK_SELECT = [
    "id",
    "project_id",
    "title",
    "description",
    "acceptance_criteria",
    "status",
    "priority",
    "difficulty",
    "story_points",
    "estimated_hours",
    "actual_hours",
    "assigned_to",
    "milestone_id",
    "sprint_id",
    "labels",
    "position",
    "start_date",
    "due_date",
    "completed_at",
    "completed_by",
    "created_at",
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def validate_difficulty(difficulty: int) -> None:
    if difficulty not in HOURS_BY_DIFFICULTY:
        raise UnprocessableEntity(
            "difficulty debe estar entre 1 y 5", details={"difficulty": difficulty}
        )


def validate_priority(priority: str) -> None:
    if priority not in PRIORITIES:
        raise UnprocessableEntity(
            f"priority debe ser uno de {sorted(PRIORITIES)}",
            details={"priority": priority},
        )


def validate_story_points(story_points: int | None) -> None:
    if story_points is not None and story_points not in STORY_POINTS:
        raise UnprocessableEntity(
            f"story_points debe ser uno de {sorted(STORY_POINTS)}",
            details={"story_points": story_points},
        )


async def _validate_status(
    client: ServiceClient, tenant: str, *, project_id: str, status: str
) -> None:
    columns = await list_columns(client, tenant, project_id=project_id)
    valid = {c["key"] for c in columns}
    if status not in valid:
        raise UnprocessableEntity(
            f"'{status}' no es una columna del tablero de este proyecto",
            details={"status": status, "valid": sorted(valid)},
        )


async def _next_position(
    client: ServiceClient, tenant: str, *, project_id: str, status: str
) -> int:
    rows = await gdb_query(
        client,
        tenant,
        table="pm_tasks",
        select=["position"],
        where={
            "project_id": project_id,
            "status": status,
            "deleted_at": {"is_null": True},
        },
        order_by=[{"field": "position", "direction": "desc"}],
        limit=1,
    )
    return (rows[0]["position"] + 1) if rows else 0


async def create_task(
    client: ServiceClient,
    tenant: str,
    *,
    project_id: str,
    title: str,
    description: str,
    acceptance_criteria: str,
    status: str,
    priority: str,
    difficulty: int,
    story_points: int | None,
    estimated_hours: float | None,
    assigned_to: str | None,
    milestone_id: str | None,
    sprint_id: str | None,
    labels: list[str],
    start_date: str | None,
    due_date: str | None,
    depends_on: list[str],
) -> dict[str, Any]:
    validate_priority(priority)
    validate_story_points(story_points)
    validate_difficulty(difficulty)
    await _validate_status(client, tenant, project_id=project_id, status=status)

    for dep_id in depends_on:
        await get_task(client, tenant, task_id=dep_id)

    task_id = new_id("tsk")
    position = await _next_position(
        client, tenant, project_id=project_id, status=status
    )
    await gdb_mutate(
        client,
        tenant,
        table="pm_tasks",
        action="insert",
        data={
            "id": task_id,
            "project_id": project_id,
            "title": title,
            "description": description,
            "acceptance_criteria": acceptance_criteria,
            "status": status,
            "priority": priority,
            "difficulty": difficulty,
            "story_points": story_points,
            "estimated_hours": estimated_hours or HOURS_BY_DIFFICULTY[difficulty],
            "assigned_to": assigned_to,
            "milestone_id": milestone_id,
            "sprint_id": sprint_id,
            "labels": labels,
            "position": position,
            "start_date": start_date,
            "due_date": due_date,
        },
    )
    for dep_id in depends_on:
        await gdb_mutate(
            client,
            tenant,
            table="pm_task_dependencies",
            action="insert",
            data={"task_id": task_id, "depends_on_task_id": dep_id},
        )

    return await get_task(client, tenant, task_id=task_id)


async def get_task(
    client: ServiceClient, tenant: str, *, task_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="pm_tasks",
        select=_TASK_SELECT,
        where={"id": task_id, "deleted_at": {"is_null": True}},
        limit=1,
    )
    if not rows:
        raise NotFound(f"La task '{task_id}' no existe", details={"task_id": task_id})
    return rows[0]


async def list_tasks(
    client: ServiceClient,
    tenant: str,
    *,
    project_id: str,
    status: str | None = None,
    sprint_id: str | None = None,
    milestone_id: str | None = None,
    assigned_to: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    where: dict[str, Any] = {"project_id": project_id, "deleted_at": {"is_null": True}}
    if status:
        where["status"] = status
    if sprint_id:
        where["sprint_id"] = sprint_id
    if milestone_id:
        where["milestone_id"] = milestone_id
    if assigned_to:
        where["assigned_to"] = assigned_to
    return await gdb_query(
        client,
        tenant,
        table="pm_tasks",
        select=_TASK_SELECT,
        where=where,
        order_by=[{"field": "position", "direction": "asc"}],
        limit=limit,
    )


async def list_dependencies(
    client: ServiceClient, tenant: str, *, task_id: str
) -> list[str]:
    rows = await gdb_query(
        client,
        tenant,
        table="pm_task_dependencies",
        select=["depends_on_task_id"],
        where={"task_id": task_id},
        limit=200,
    )
    return [r["depends_on_task_id"] for r in rows]


async def _is_blocked(client: ServiceClient, tenant: str, *, task_id: str) -> list[str]:
    """Devuelve las dependencias que todavía no están en 'done'."""
    blocking = []
    for dep_id in await list_dependencies(client, tenant, task_id=task_id):
        dep = await get_task(client, tenant, task_id=dep_id)
        if dep["status"] != DONE_STATUS:
            blocking.append(dep_id)
    return blocking


async def update_task(
    client: ServiceClient,
    tenant: str,
    *,
    task_id: str,
    status: str | None,
    priority: str | None,
    assigned_to: str | None,
    actual_hours: float | None,
    position: int | None,
    completed_by: str | None,
) -> dict[str, Any]:
    task = await get_task(client, tenant, task_id=task_id)

    data: dict[str, Any] = {}
    if priority is not None:
        validate_priority(priority)
        data["priority"] = priority
    if assigned_to is not None:
        data["assigned_to"] = assigned_to
    if actual_hours is not None:
        data["actual_hours"] = actual_hours

    if status is not None and status != task["status"]:
        # Pedido explícito del usuario: una task en "done" queda cerrada --
        # ya no se puede mover a ningún otro estado (antes sí se podía
        # reabrir; ver DECISIONS.md para el motivo del cambio).
        if task["status"] == DONE_STATUS:
            raise Conflict(
                "La task ya está en 'done' -- no se puede mover",
                details={"task_id": task_id, "status": task["status"]},
            )
        await _validate_status(
            client, tenant, project_id=task["project_id"], status=status
        )
        if status not in _UNBLOCKED_STATUSES:
            blocking = await _is_blocked(client, tenant, task_id=task_id)
            if blocking:
                raise Conflict(
                    f"La task tiene dependencias sin completar: no puede pasar a "
                    f"'{status}'",
                    details={"blocking_task_ids": blocking},
                )
        data["status"] = status
        # Si el caller ya manda la posición deseada dentro de la columna
        # destino (arrastrar y soltar entre dos tarjetas, no sólo al final),
        # respetarla -- antes esta rama siempre pisaba position con
        # _next_position (al final), ignorando en silencio cualquier
        # posición que el caller hubiera mandado junto con el cambio de
        # status.
        data["position"] = (
            position
            if position is not None
            else await _next_position(
                client, tenant, project_id=task["project_id"], status=status
            )
        )
        if status == DONE_STATUS:
            data["completed_at"] = _now()
            data["completed_by"] = completed_by
        # No hace falta una rama para "reabrir desde done": ya no es
        # alcanzable -- el guard de arriba lo rechaza antes de llegar aquí.
    elif position is not None:
        data["position"] = position

    if not data:
        return task

    await gdb_mutate(
        client,
        tenant,
        table="pm_tasks",
        action="update",
        where={"id": task_id},
        data=data,
    )
    return await get_task(client, tenant, task_id=task_id)


async def delete_task(client: ServiceClient, tenant: str, *, task_id: str) -> None:
    await get_task(client, tenant, task_id=task_id)
    await gdb_mutate(
        client,
        tenant,
        table="pm_tasks",
        action="update",
        where={"id": task_id},
        data={"deleted_at": _now()},
    )
