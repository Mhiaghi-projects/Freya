"""Developer Portal (docs/ROADMAP.md Fase 9, punto 4): proxy delgado sobre
project-manager/app/api/{projects,tasks}.py."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from freya_common import ServiceClient
from pydantic import BaseModel

from app.infra.gateway import client_dep

router = APIRouter(prefix="/api/projects", tags=["projects"])
ProjectManagerClient = Annotated[ServiceClient, Depends(client_dep("project-manager"))]


class TaskStatusUpdate(BaseModel):
    status: str


@router.get("")
async def list_projects(client: ProjectManagerClient) -> list:
    return ServiceClient.data(await client.get("/projects"))


@router.get("/{project_id}")
async def get_project(project_id: str, client: ProjectManagerClient) -> dict:
    return ServiceClient.data(await client.get(f"/projects/{project_id}"))


@router.get("/{project_id}/kanban")
async def get_kanban(project_id: str, client: ProjectManagerClient) -> dict:
    return ServiceClient.data(await client.get(f"/projects/{project_id}/kanban"))


@router.get("/{project_id}/tasks")
async def list_tasks(
    project_id: str,
    client: ProjectManagerClient,
    status: str | None = None,
    assigned_to: str | None = None,
) -> list:
    raw_params = {"status": status, "assigned_to": assigned_to}
    params = {k: v for k, v in raw_params.items() if v}
    response = await client.get(f"/projects/{project_id}/tasks", params=params)
    return ServiceClient.data(response)


@router.put("/tasks/{task_id}")
async def update_task_status(
    task_id: str, body: TaskStatusUpdate, client: ProjectManagerClient
) -> dict:
    response = await client.put(f"/tasks/{task_id}", json={"status": body.status})
    return ServiceClient.data(response)
