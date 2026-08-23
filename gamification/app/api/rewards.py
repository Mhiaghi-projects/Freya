"""Expense Rewards (docs/ROADMAP.md Fase 10) -- ver app/domain/rewards.py
para la interpretación del nombre."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant
from pydantic import BaseModel, Field

from app.deps import UserIdDep
from app.domain.rewards import (
    archive_reward,
    create_reward,
    list_rewards,
    redeem_reward,
)

router = APIRouter(prefix="/rewards", tags=["rewards"])


class RewardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    coin_cost: int = Field(gt=0)


@router.get("")
async def list_route(user_id: UserIdDep, request: Request) -> list:
    return await list_rewards(request.app.state.gestor_db, current_tenant(), user_id)


@router.post("", status_code=201)
async def create_route(
    body: RewardCreate, user_id: UserIdDep, request: Request
) -> dict:
    client, tenant = request.app.state.gestor_db, current_tenant()
    return await create_reward(
        client, tenant, user_id=user_id, name=body.name, coin_cost=body.coin_cost
    )


@router.post("/{reward_id}/redeem")
async def redeem_route(reward_id: str, user_id: UserIdDep, request: Request) -> dict:
    client, tenant = request.app.state.gestor_db, current_tenant()
    return await redeem_reward(client, tenant, reward_id=reward_id, user_id=user_id)


@router.delete("/{reward_id}", status_code=204)
async def archive_route(reward_id: str, user_id: UserIdDep, request: Request) -> None:
    client, tenant = request.app.state.gestor_db, current_tenant()
    await archive_reward(client, tenant, reward_id=reward_id, user_id=user_id)
