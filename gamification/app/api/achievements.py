"""Catálogo de logros y desbloqueos propios."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant

from app.deps import UserIdDep
from app.domain.achievements import list_for_user

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("")
async def list_achievements(user_id: UserIdDep, request: Request) -> list:
    return await list_for_user(request.app.state.gestor_db, current_tenant(), user_id)
