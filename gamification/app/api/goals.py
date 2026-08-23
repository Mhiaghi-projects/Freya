"""Metas diarias/semanales/mensuales/anuales (docs/ROADMAP.md Fase 10)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant
from pydantic import BaseModel, Field

from app.deps import UserIdDep
from app.domain.goals import archive_goal, create_goal, list_goals

router = APIRouter(prefix="/goals", tags=["goals"])


class GoalCreate(BaseModel):
    period: str = Field(pattern="^(daily|weekly|monthly|annual)$")
    target_type: str = Field(pattern="^(tasks_completed|xp_earned)$")
    target_value: int = Field(gt=0)


@router.get("")
async def list_route(user_id: UserIdDep, request: Request) -> list:
    return await list_goals(request.app.state.gestor_db, current_tenant(), user_id)


@router.post("", status_code=201)
async def create_route(body: GoalCreate, user_id: UserIdDep, request: Request) -> dict:
    return await create_goal(
        request.app.state.gestor_db,
        current_tenant(),
        user_id=user_id,
        period=body.period,
        target_type=body.target_type,
        target_value=body.target_value,
    )


@router.delete("/{goal_id}", status_code=204)
async def archive_route(goal_id: str, user_id: UserIdDep, request: Request) -> None:
    await archive_goal(
        request.app.state.gestor_db, current_tenant(), goal_id=goal_id, user_id=user_id
    )
