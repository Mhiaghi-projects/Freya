"""Habit Tracker (docs/ROADMAP.md Fase 10)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant
from pydantic import BaseModel, Field

from app.deps import UserIdDep
from app.domain.habits import archive_habit, create_habit, list_habits, log_habit

router = APIRouter(prefix="/habits", tags=["habits"])


class HabitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    frequency: str = Field(default="daily")


@router.get("")
async def list_route(user_id: UserIdDep, request: Request) -> list:
    return await list_habits(request.app.state.gestor_db, current_tenant(), user_id)


@router.post("", status_code=201)
async def create_route(body: HabitCreate, user_id: UserIdDep, request: Request) -> dict:
    return await create_habit(
        request.app.state.gestor_db,
        current_tenant(),
        user_id=user_id,
        name=body.name,
        frequency=body.frequency,
    )


@router.post("/{habit_id}/log")
async def log_route(habit_id: str, user_id: UserIdDep, request: Request) -> dict:
    client, tenant = request.app.state.gestor_db, current_tenant()
    return await log_habit(client, tenant, habit_id=habit_id, user_id=user_id)


@router.delete("/{habit_id}", status_code=204)
async def archive_route(habit_id: str, user_id: UserIdDep, request: Request) -> None:
    client, tenant = request.app.state.gestor_db, current_tenant()
    await archive_habit(client, tenant, habit_id=habit_id, user_id=user_id)
