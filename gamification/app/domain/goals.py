"""Metas diarias/semanales/mensuales/anuales (docs/ROADMAP.md Fase 10).

period_start se calcula solo, al crear la meta, a partir de "period" y hoy
-- no hay reinicio automático al terminar el periodo (crear una meta nueva
para el siguiente periodo es la manera de "reiniciar"; ver
docs/DECISIONS.md, entrada de gamification, para el porqué de no construir
un sistema de reinicio recurrente todavía)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from freya_common import BadRequest, ServiceClient, gdb_mutate, gdb_query, new_id

_PERIODS = {"daily", "weekly", "monthly", "annual"}
_TARGET_TYPES = {"tasks_completed", "xp_earned"}


def _period_start(period: str, today: date) -> date:
    if period == "daily":
        return today
    if period == "weekly":
        return today - timedelta(days=today.weekday())
    if period == "monthly":
        return today.replace(day=1)
    return today.replace(month=1, day=1)


async def create_goal(
    client: ServiceClient,
    tenant: str,
    *,
    user_id: str,
    period: str,
    target_type: str,
    target_value: int,
) -> dict[str, Any]:
    if period not in _PERIODS:
        raise BadRequest(
            f"period desconocido: '{period}'", details={"known": list(_PERIODS)}
        )
    if target_type not in _TARGET_TYPES:
        raise BadRequest(
            f"target_type desconocido: '{target_type}'",
            details={"known": list(_TARGET_TYPES)},
        )
    if target_value <= 0:
        raise BadRequest("target_value debe ser mayor que cero")

    goal_id = new_id("gol")
    period_start = _period_start(period, datetime.now(UTC).date())
    await gdb_mutate(
        client,
        tenant,
        table="gam_goals",
        action="insert",
        data={
            "id": goal_id,
            "user_id": user_id,
            "period": period,
            "target_type": target_type,
            "target_value": target_value,
            "period_start": period_start.isoformat(),
        },
    )
    return {
        "id": goal_id,
        "user_id": user_id,
        "period": period,
        "target_type": target_type,
        "target_value": target_value,
        "period_start": period_start.isoformat(),
    }


async def _progress(client: ServiceClient, tenant: str, goal: dict[str, Any]) -> int:
    # 200 es el tope real de gestor-db (QueryRequest.limit, le=200) -- una
    # meta anual puede acumular más eventos que eso para alguien muy
    # activo, así que aquí sí hace falta paginar de verdad (mismo patrón
    # que gestor-monitoring:uptime_percent_24h).
    events: list[dict] = []
    offset = 0
    while True:
        page = await gdb_query(
            client,
            tenant,
            table="gam_xp_events",
            select=["xp", "source"],
            where={
                "user_id": goal["user_id"],
                "created_at": {"gte": f"{goal['period_start']}T00:00:00Z"},
            },
            limit=200,
            offset=offset,
        )
        events.extend(page)
        if len(page) < 200:
            break
        offset += 200

    if goal["target_type"] == "xp_earned":
        return sum(e["xp"] for e in events)
    return sum(1 for e in events if e["source"] == "task_completed")


async def list_goals(
    client: ServiceClient, tenant: str, user_id: str
) -> list[dict[str, Any]]:
    goals = await gdb_query(
        client,
        tenant,
        table="gam_goals",
        where={"user_id": user_id, "archived_at": {"is_null": True}},
        order_by=[{"field": "created_at", "direction": "desc"}],
    )
    for goal in goals:
        goal["progress"] = await _progress(client, tenant, goal)
        goal["completed"] = goal["progress"] >= goal["target_value"]
    return goals


async def archive_goal(
    client: ServiceClient, tenant: str, *, goal_id: str, user_id: str
) -> None:
    await gdb_mutate(
        client,
        tenant,
        table="gam_goals",
        action="update",
        where={"id": goal_id, "user_id": user_id},
        data={"archived_at": datetime.now(UTC).isoformat()},
    )
