"""Tasks (docs/freya-api-contract.md §7.2, §7.3, §7.4)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from freya_common import current_tenant, require_permissions, require_service_access

from app.deps import ClaimsDep
from app.domain.commits import link_commit, list_commits_for_task
from app.domain.projects import get_project
from app.domain.tasks import create_task, delete_task, get_task, list_tasks, update_task
from app.models.requests import CommitLink, TaskCreate, TaskUpdate

router = APIRouter(tags=["tasks"])


@router.post("/projects/{project_id}/tasks", status_code=201)
async def create(
    project_id: str, body: TaskCreate, claims: ClaimsDep, request: Request
) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:project-manager")
    client = request.app.state.gestor_db
    await get_project(client, tenant, project_id=project_id)
    return await create_task(
        client,
        tenant,
        project_id=project_id,
        title=body.title,
        description=body.description,
        acceptance_criteria=body.acceptance_criteria,
        status=body.status,
        priority=body.priority,
        difficulty=body.difficulty,
        story_points=body.story_points,
        estimated_hours=body.estimated_hours,
        assigned_to=body.assigned_to,
        milestone_id=body.milestone_id,
        sprint_id=body.sprint_id,
        labels=body.labels,
        start_date=body.start_date,
        due_date=body.due_date,
        depends_on=body.depends_on,
    )


@router.get("/projects/{project_id}/tasks")
async def list_all(
    project_id: str,
    claims: ClaimsDep,
    request: Request,
    status: str | None = Query(default=None),
    sprint_id: str | None = Query(default=None),
    milestone_id: str | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
) -> list[dict]:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:project-manager")
    return await list_tasks(
        request.app.state.gestor_db,
        tenant,
        project_id=project_id,
        status=status,
        sprint_id=sprint_id,
        milestone_id=milestone_id,
        assigned_to=assigned_to,
    )


@router.get("/tasks/{task_id}")
async def get(task_id: str, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:project-manager")
    return await get_task(request.app.state.gestor_db, tenant, task_id=task_id)


@router.put("/tasks/{task_id}")
async def update(
    task_id: str, body: TaskUpdate, claims: ClaimsDep, request: Request
) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:project-manager")
    completed_by = str(claims.get("sub") or claims.get("service") or "")
    return await update_task(
        request.app.state.gestor_db,
        tenant,
        task_id=task_id,
        status=body.status,
        priority=body.priority,
        assigned_to=body.assigned_to,
        actual_hours=body.actual_hours,
        position=body.position,
        completed_by=completed_by or None,
    )


@router.delete("/tasks/{task_id}", status_code=204)
async def remove(task_id: str, claims: ClaimsDep, request: Request) -> None:
    # admin:project-manager sigue siendo un permiso plano de rol, mismo
    # criterio que borrar un proyecto entero (ver projects.py:remove).
    require_permissions(claims, "admin:project-manager")
    await delete_task(request.app.state.gestor_db, current_tenant(), task_id=task_id)


@router.post("/tasks/{task_id}/link-commit", status_code=201)
async def link_commit_route(
    task_id: str, body: CommitLink, claims: ClaimsDep, request: Request
) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:project-manager")
    client = request.app.state.gestor_db
    await get_task(client, tenant, task_id=task_id)
    return await link_commit(
        client,
        tenant,
        task_id=task_id,
        repo_id=body.repo_id,
        commit_hash=body.commit_hash,
    )


@router.get("/tasks/{task_id}/commits")
async def commits_route(
    task_id: str, claims: ClaimsDep, request: Request
) -> list[dict]:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:project-manager")
    return await list_commits_for_task(
        request.app.state.gestor_db, tenant, task_id=task_id
    )
