"""Mi Progreso (docs/ROADMAP.md Fase 10): proxy delgado sobre gamification."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from freya_common import ServiceClient
from pydantic import BaseModel, Field

from app.infra.gateway import client_dep

router = APIRouter(prefix="/api/gamification", tags=["gamification"])
GamClient = Annotated[ServiceClient, Depends(client_dep("gamification"))]


class HabitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    frequency: str = Field(default="daily")


class RewardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    coin_cost: int = Field(gt=0)


class GoalCreate(BaseModel):
    period: str
    target_type: str
    target_value: int = Field(gt=0)


@router.get("/me")
async def me(client: GamClient) -> dict:
    return ServiceClient.data(await client.get("/me"))


@router.get("/leaderboard")
async def leaderboard(client: GamClient) -> list:
    return ServiceClient.data(await client.get("/leaderboard"))


@router.get("/achievements")
async def achievements(client: GamClient) -> list:
    return ServiceClient.data(await client.get("/achievements"))


@router.get("/habits")
async def list_habits(client: GamClient) -> list:
    return ServiceClient.data(await client.get("/habits"))


@router.post("/habits", status_code=201)
async def create_habit(body: HabitCreate, client: GamClient) -> dict:
    return ServiceClient.data(await client.post("/habits", json=body.model_dump()))


@router.post("/habits/{habit_id}/log")
async def log_habit(habit_id: str, client: GamClient) -> dict:
    return ServiceClient.data(await client.post(f"/habits/{habit_id}/log"))


@router.delete("/habits/{habit_id}", status_code=204)
async def archive_habit(habit_id: str, client: GamClient) -> None:
    await client.delete(f"/habits/{habit_id}")


@router.get("/rewards")
async def list_rewards(client: GamClient) -> list:
    return ServiceClient.data(await client.get("/rewards"))


@router.post("/rewards", status_code=201)
async def create_reward(body: RewardCreate, client: GamClient) -> dict:
    return ServiceClient.data(await client.post("/rewards", json=body.model_dump()))


@router.post("/rewards/{reward_id}/redeem")
async def redeem_reward(reward_id: str, client: GamClient) -> dict:
    return ServiceClient.data(await client.post(f"/rewards/{reward_id}/redeem"))


@router.delete("/rewards/{reward_id}", status_code=204)
async def archive_reward(reward_id: str, client: GamClient) -> None:
    await client.delete(f"/rewards/{reward_id}")


@router.get("/goals")
async def list_goals(client: GamClient) -> list:
    return ServiceClient.data(await client.get("/goals"))


@router.post("/goals", status_code=201)
async def create_goal(body: GoalCreate, client: GamClient) -> dict:
    return ServiceClient.data(await client.post("/goals", json=body.model_dump()))


@router.delete("/goals/{goal_id}", status_code=204)
async def archive_goal(goal_id: str, client: GamClient) -> None:
    await client.delete(f"/goals/{goal_id}")
