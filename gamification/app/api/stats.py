"""Estadísticas propias y leaderboard (docs/ROADMAP.md Fase 10)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from freya_common import current_tenant

from app.deps import UserIdDep
from app.domain.leveling import xp_to_next_level
from app.domain.stats import get_stats
from app.domain.stats import leaderboard as leaderboard_query

router = APIRouter(tags=["stats"])


@router.get("/me")
async def me(user_id: UserIdDep, request: Request) -> dict:
    stats = await get_stats(request.app.state.gestor_db, current_tenant(), user_id)
    return {**stats, **xp_to_next_level(stats["total_xp"])}


@router.get("/leaderboard")
async def leaderboard(
    user_id: UserIdDep,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    period: str = Query(default="weekly", pattern="^(weekly|alltime)$"),
) -> list:
    del user_id  # sólo para exigir sesión de usuario, no se usa
    client, tenant = request.app.state.gestor_db, current_tenant()
    rows = await leaderboard_query(client, tenant, limit=limit, period=period)
    return [{"rank": i + 1, **row} for i, row in enumerate(rows)]
