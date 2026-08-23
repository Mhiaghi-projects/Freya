"""Habit Tracker (docs/ROADMAP.md Fase 10)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from freya_common import Conflict, ServiceClient, gdb_mutate, gdb_query, new_id

_FREQUENCIES = {"daily", "weekly"}


async def create_habit(
    client: ServiceClient, tenant: str, *, user_id: str, name: str, frequency: str
) -> dict[str, Any]:
    if frequency not in _FREQUENCIES:
        frequency = "daily"
    habit_id = new_id("hab")
    await gdb_mutate(
        client,
        tenant,
        table="gam_habits",
        action="insert",
        data={"id": habit_id, "user_id": user_id, "name": name, "frequency": frequency},
    )
    return {"id": habit_id, "user_id": user_id, "name": name, "frequency": frequency}


async def list_habits(
    client: ServiceClient, tenant: str, user_id: str
) -> list[dict[str, Any]]:
    habits = await gdb_query(
        client,
        tenant,
        table="gam_habits",
        where={"user_id": user_id, "archived_at": {"is_null": True}},
        order_by=[{"field": "created_at", "direction": "asc"}],
    )
    for habit in habits:
        logs = await gdb_query(
            client,
            tenant,
            table="gam_habit_logs",
            select=["logged_date"],
            where={"habit_id": habit["id"]},
            order_by=[{"field": "logged_date", "direction": "desc"}],
            limit=200,  # tope real de gestor-db (QueryRequest.limit, le=200)
        )
        habit["streak"] = _current_streak({row["logged_date"] for row in logs})
        habit["logged_today"] = date.today().isoformat() in {
            row["logged_date"] for row in logs
        }
    return habits


def _current_streak(logged_dates: set[str]) -> int:
    if not logged_dates:
        return 0
    parsed = sorted((date.fromisoformat(d) for d in logged_dates), reverse=True)
    today = date.today()
    if parsed[0] not in (today, today - timedelta(days=1)):
        return 0
    streak = 1
    for i in range(1, len(parsed)):
        if (parsed[i - 1] - parsed[i]).days == 1:
            streak += 1
        else:
            break
    return streak


async def log_habit(
    client: ServiceClient, tenant: str, *, habit_id: str, user_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client, tenant, table="gam_habits", where={"id": habit_id, "user_id": user_id}
    )
    if not rows:
        raise Conflict("hábito desconocido o de otro usuario")

    today = date.today().isoformat()
    existing = await gdb_query(
        client,
        tenant,
        table="gam_habit_logs",
        where={"habit_id": habit_id, "logged_date": today},
    )
    if existing:
        return {"habit_id": habit_id, "logged_date": today, "already_logged": True}

    await gdb_mutate(
        client,
        tenant,
        table="gam_habit_logs",
        action="insert",
        data={
            "id": new_id("hlg"),
            "habit_id": habit_id,
            "logged_date": today,
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    return {"habit_id": habit_id, "logged_date": today, "already_logged": False}


async def archive_habit(
    client: ServiceClient, tenant: str, *, habit_id: str, user_id: str
) -> None:
    await gdb_mutate(
        client,
        tenant,
        table="gam_habits",
        action="update",
        where={"id": habit_id, "user_id": user_id},
        data={"archived_at": datetime.now(UTC).isoformat()},
    )
