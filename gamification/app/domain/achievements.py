"""Catálogo fijo de logros y su desbloqueo. Igual que los roles de auth
(ROLE_PERMISSIONS): una tabla en código, no un motor de reglas -- se amplía
añadiendo una entrada aquí, no con una API de administración."""

from __future__ import annotations

from typing import Any

from freya_common import ServiceClient, gdb_mutate, gdb_query, new_id

CATALOG: list[dict[str, str]] = [
    {"code": "first_task", "name": "Primer paso", "icon": "🎯",
     "description": "Completa tu primera task."},
    {"code": "ten_tasks", "name": "En racha", "icon": "🔥",
     "description": "Completa 10 tasks."},
    {"code": "fifty_tasks", "name": "Imparable", "icon": "🚀",
     "description": "Completa 50 tasks."},
    {"code": "level_5", "name": "Subiendo", "icon": "⭐",
     "description": "Alcanza el nivel 5."},
    {"code": "level_10", "name": "Veterano", "icon": "🏅",
     "description": "Alcanza el nivel 10."},
    {"code": "streak_7", "name": "Semana perfecta", "icon": "📅",
     "description": "7 días seguidos de actividad."},
    {"code": "streak_30", "name": "Mes de hierro", "icon": "💎",
     "description": "30 días seguidos de actividad."},
]

_CATALOG_BY_CODE = {a["code"]: a for a in CATALOG}


async def seed_catalog(client: ServiceClient, tenant: str) -> None:
    for achievement in CATALOG:
        await gdb_mutate(
            client,
            tenant,
            table="gam_achievements",
            action="upsert",
            data=achievement,
            conflict_target=["code"],
        )


async def unlocked_codes(client: ServiceClient, tenant: str, user_id: str) -> set[str]:
    rows = await gdb_query(
        client,
        tenant,
        table="gam_achievement_unlocks",
        select=["achievement_code"],
        where={"user_id": user_id},
        limit=len(CATALOG),
    )
    return {r["achievement_code"] for r in rows}


def _eligible_codes(*, task_count: int, level: int, current_streak: int) -> set[str]:
    codes = set()
    if task_count >= 1:
        codes.add("first_task")
    if task_count >= 10:
        codes.add("ten_tasks")
    if task_count >= 50:
        codes.add("fifty_tasks")
    if level >= 5:
        codes.add("level_5")
    if level >= 10:
        codes.add("level_10")
    if current_streak >= 7:
        codes.add("streak_7")
    if current_streak >= 30:
        codes.add("streak_30")
    return codes


async def check_and_unlock(
    client: ServiceClient,
    tenant: str,
    *,
    user_id: str,
    task_count: int,
    level: int,
    current_streak: int,
) -> list[dict[str, str]]:
    already = await unlocked_codes(client, tenant, user_id)
    eligible = _eligible_codes(
        task_count=task_count, level=level, current_streak=current_streak
    )
    newly_unlocked = eligible - already

    for code in newly_unlocked:
        await gdb_mutate(
            client,
            tenant,
            table="gam_achievement_unlocks",
            action="insert",
            data={
                "id": new_id("aun"),
                "user_id": user_id,
                "achievement_code": code,
            },
        )
    return [_CATALOG_BY_CODE[code] for code in newly_unlocked]


async def list_for_user(
    client: ServiceClient, tenant: str, user_id: str
) -> list[dict[str, Any]]:
    unlocked = await unlocked_codes(client, tenant, user_id)
    return [{**a, "unlocked": a["code"] in unlocked} for a in CATALOG]
