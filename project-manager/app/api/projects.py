"""Proyectos y tablero Kanban (docs/freya-api-contract.md §7.1, §7.5)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant, require_permissions, require_service_access

from app.deps import ClaimsDep
from app.domain.projects import (
    create_project,
    delete_project,
    get_project,
    list_columns,
    list_projects,
)
from app.domain.tasks import list_tasks
from app.models.requests import ProjectCreate

router = APIRouter(tags=["projects"])


@router.post("/projects", status_code=201)
async def create(body: ProjectCreate, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:project-manager")
    return await create_project(
        request.app.state.gestor_db,
        tenant,
        project_name=body.project_name,
        description=body.description,
        project_type=body.project_type,
        visibility=body.visibility,
        difficulty=body.difficulty,
        linked_git_repo=body.linked_git_repo,
        ci_cd_enabled=body.ci_cd_enabled,
        team_members=body.team_members,
    )


@router.get("/projects")
async def list_all(claims: ClaimsDep, request: Request) -> list[dict]:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:project-manager")
    return await list_projects(request.app.state.gestor_db, tenant)


@router.get("/projects/{project_id}")
async def get(project_id: str, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:project-manager")
    return await get_project(
        request.app.state.gestor_db, tenant, project_id=project_id
    )


@router.delete("/projects/{project_id}", status_code=204)
async def remove(project_id: str, claims: ClaimsDep, request: Request) -> None:
    # admin:project-manager sigue siendo un permiso plano de rol, no un
    # acceso por proyecto -- borrar un proyecto entero es cosa de
    # administración de verdad, mismo criterio que admin:git.
    require_permissions(claims, "admin:project-manager")
    await delete_project(
        request.app.state.gestor_db, current_tenant(), project_id=project_id
    )


@router.get("/projects/{project_id}/kanban")
async def kanban(project_id: str, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:project-manager")
    client = request.app.state.gestor_db
    await get_project(client, tenant, project_id=project_id)
    columns = await list_columns(client, tenant, project_id=project_id)

    board = []
    for column in columns:
        tasks = await list_tasks(
            client, tenant, project_id=project_id, status=column["key"]
        )
        board.append(
            {
                "status": column["key"],
                "label": column["label"],
                "task_count": len(tasks),
                "tasks": [
                    {
                        "task_id": t["id"],
                        "title": t["title"],
                        "priority": t["priority"],
                        "story_points": t["story_points"],
                        "assigned_to": t["assigned_to"],
                        "due_date": t["due_date"],
                    }
                    for t in tasks
                ],
            }
        )
    return {"project_id": project_id, "columns": board}
