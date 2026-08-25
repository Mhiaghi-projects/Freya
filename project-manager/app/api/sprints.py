"""Sprints (docs/freya-api-contract.md §7.6)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from freya_common import current_tenant, require_service_access

from app.deps import ClaimsDep
from app.domain.projects import get_project
from app.domain.sprints import (
    create_sprint,
    list_sprints,
    sprint_metrics,
    update_sprint,
)
from app.models.requests import SprintCreate, SprintUpdate

router = APIRouter(tags=["sprints"])


@router.post("/projects/{project_id}/sprints", status_code=201)
async def create(
    project_id: str, body: SprintCreate, claims: ClaimsDep, request: Request
) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:project-manager")
    client = request.app.state.gestor_db
    await get_project(client, tenant, project_id=project_id)
    return await create_sprint(
        client,
        tenant,
        project_id=project_id,
        name=body.name,
        goal=body.goal,
        start_date=body.start_date,
        end_date=body.end_date,
        task_ids=body.task_ids,
    )


@router.get("/projects/{project_id}/sprints")
async def list_all(
    project_id: str,
    claims: ClaimsDep,
    request: Request,
    status: str | None = Query(default=None),
) -> list[dict]:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:project-manager")
    return await list_sprints(
        request.app.state.gestor_db,
        tenant,
        project_id=project_id,
        status=status,
    )


@router.get("/projects/{project_id}/sprints/{sprint_id}")
async def get(
    project_id: str, sprint_id: str, claims: ClaimsDep, request: Request
) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:project-manager")
    return await sprint_metrics(
        request.app.state.gestor_db,
        tenant,
        sprint_id=sprint_id,
        project_id=project_id,
    )


@router.put("/projects/{project_id}/sprints/{sprint_id}")
async def update(
    project_id: str,
    sprint_id: str,
    body: SprintUpdate,
    claims: ClaimsDep,
    request: Request,
) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:project-manager")
    return await update_sprint(
        request.app.state.gestor_db,
        tenant,
        sprint_id=sprint_id,
        project_id=project_id,
        status=body.status,
    )
