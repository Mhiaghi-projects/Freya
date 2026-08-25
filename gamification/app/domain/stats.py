"""Estadísticas por usuario: XP, nivel, monedas, racha. Toda mutación pasa
por award_xp -- es el único punto que sabe combinar nivel + racha de forma
consistente (docs/ROADMAP.md Fase 10, criterio de salida)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from freya_common import ServiceClient, gdb_mutate, gdb_query

from app.domain.leveling import level_for_xp

# Fuentes de gam_xp_events que representan "una tarea completada" a efectos
# de logros/metas -- task_sync.py (project-manager) y github_task_sync.py
# (Issues de GitHub) son dos vías independientes hacia el mismo contador
# lógico. Cada syncer sólo veía su propia fuente al calcular task_count
# (achievements.check_and_unlock) o "tasks_completed" (goals._progress), así
# que un usuario con completions de las dos vías quedaba subcontado en
# ambos sitios aunque gam_xp_events (source, source_ref) UNIQUE ya impide
# que se duplique el XP en sí -- ver docs/DECISIONS.md.
TASK_COMPLETION_SOURCES = ("task_completed", "github_issue")

_DEFAULT_STATS = {
    "total_xp": 0,
    "level": 1,
    "coins": 0,
    "current_streak": 0,
    "longest_streak": 0,
    "last_activity_date": None,
    "weekly_xp": 0,
    "weekly_coins": 0,
}


async def get_stats(client: ServiceClient, tenant: str, user_id: str) -> dict[str, Any]:
    rows = await gdb_query(
        client, tenant, table="gam_user_stats", where={"user_id": user_id}
    )
    if rows:
        return rows[0]
    return {"user_id": user_id, **_DEFAULT_STATS}


async def count_completed_tasks(
    client: ServiceClient, tenant: str, user_id: str
) -> int:
    """Cuenta tareas completadas del usuario a través de TODAS las fuentes
    de sync (ver TASK_COMPLETION_SOURCES) -- pagina de verdad porque 200
    (tope real de gestor-db, QueryRequest.limit) es alcanzable para alguien
    activo entre dos vías de sync a la vez."""
    total = 0
    offset = 0
    while True:
        page = await gdb_query(
            client,
            tenant,
            table="gam_xp_events",
            select=["id"],
            where={"user_id": user_id, "source": {"in": TASK_COMPLETION_SOURCES}},
            limit=200,
            offset=offset,
        )
        total += len(page)
        if len(page) < 200:
            return total
        offset += 200


async def _ensure_row(client: ServiceClient, tenant: str, user_id: str) -> None:
    rows = await gdb_query(
        client, tenant, table="gam_user_stats", where={"user_id": user_id}
    )
    if not rows:
        await gdb_mutate(
            client,
            tenant,
            table="gam_user_stats",
            action="insert",
            data={"user_id": user_id, **_DEFAULT_STATS},
        )


def _apply_streak(stats: dict[str, Any], today: date) -> tuple[int, int]:
    last = stats["last_activity_date"]
    if not last:
        return 1, max(1, stats["longest_streak"])
    last_date = date.fromisoformat(last) if isinstance(last, str) else last
    delta = (today - last_date).days
    if delta <= 0:
        return stats["current_streak"], stats["longest_streak"]
    streak = stats["current_streak"] + 1 if delta == 1 else 1
    return streak, max(stats["longest_streak"], streak)


async def award_xp(
    client: ServiceClient,
    tenant: str,
    *,
    user_id: str,
    xp: int,
    coins: int,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    await _ensure_row(client, tenant, user_id)
    rows = await gdb_query(
        client, tenant, table="gam_user_stats", where={"user_id": user_id}
    )
    stats = rows[0]

    new_total = stats["total_xp"] + xp
    new_level = level_for_xp(new_total)
    leveled_up = new_level > stats["level"]
    streak, longest = _apply_streak(stats, today)
    new_weekly_xp = stats.get("weekly_xp", 0) + xp
    new_weekly_coins = stats.get("weekly_coins", 0) + coins

    await gdb_mutate(
        client,
        tenant,
        table="gam_user_stats",
        action="update",
        where={"user_id": user_id},
        data={
            "total_xp": new_total,
            "level": new_level,
            "coins": stats["coins"] + coins,
            "current_streak": streak,
            "longest_streak": longest,
            "last_activity_date": today.isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "weekly_xp": new_weekly_xp,
            "weekly_coins": new_weekly_coins,
        },
    )
    return {
        "user_id": user_id,
        "total_xp": new_total,
        "level": new_level,
        "leveled_up": leveled_up,
        "coins": stats["coins"] + coins,
        "current_streak": streak,
        "longest_streak": longest,
        "weekly_xp": new_weekly_xp,
    }


async def spend_coins(
    client: ServiceClient, tenant: str, *, user_id: str, amount: int
) -> None:
    """Descuenta monedas -- el llamador ya verificó que hay saldo suficiente
    (app/domain/rewards.py:redeem, dentro de la misma comprobación de
    negocio, para poder dar un error claro de 'saldo insuficiente' antes de
    llegar aquí)."""
    stats = await get_stats(client, tenant, user_id)
    await gdb_mutate(
        client,
        tenant,
        table="gam_user_stats",
        action="update",
        where={"user_id": user_id},
        data={"coins": stats["coins"] - amount},
    )


async def leaderboard(
    client: ServiceClient, tenant: str, *, limit: int = 20, period: str = "weekly"
) -> list[dict[str, Any]]:
    """period="weekly" (por defecto, pedido explícito del usuario: el
    leaderboard compite semana a semana, no de por vida) o "alltime"."""
    field = "weekly_xp" if period == "weekly" else "total_xp"
    return await gdb_query(
        client,
        tenant,
        table="gam_user_stats",
        order_by=[{"field": field, "direction": "desc"}],
        limit=limit,
    )
