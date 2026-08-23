"""Milestones (ROADMAP.md pm-05)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant, require_permissions

from app.deps import ClaimsDep
from app.domain.milestones import create_milestone, list_milestones, milestone_progress
from app.domain.projects import get_project
from app.models.requests import MilestoneCreate

router = APIRouter(tags=["milestones"])


@router.post("/projects/{project_id}/milestones", status_code=201)
async def create(
    project_id: str, body: MilestoneCreate, claims: ClaimsDep, request: Request
) -> dict:
    require_permissions(claims, "write:project-manager")
    tenant = current_tenant()
    client = request.app.state.gestor_db
    await get_project(client, tenant, project_id=project_id)
    return await create_milestone(
        client,
        tenant,
        project_id=project_id,
        title=body.title,
        description=body.description,
        target_date=body.target_date,
    )


@router.get("/projects/{project_id}/milestones")
async def list_all(project_id: str, claims: ClaimsDep, request: Request) -> list[dict]:
    require_permissions(claims, "read:project-manager")
    return await list_milestones(
        request.app.state.gestor_db, current_tenant(), project_id=project_id
    )


@router.get("/milestones/{milestone_id}")
async def progress(milestone_id: str, claims: ClaimsDep, request: Request) -> dict:
    require_permissions(claims, "read:project-manager")
    return await milestone_progress(
        request.app.state.gestor_db, current_tenant(), milestone_id=milestone_id
    )
