"""Vista de git (docs/ROADMAP.md Fase 9, punto 5): proxy delgado sobre la
API REST real de git/app/api/repos.py -- los permisos (read:git/write:git)
los sigue exigiendo git, no esta capa."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from freya_common import ServiceClient

from app.infra.gateway import client_dep

router = APIRouter(prefix="/api/git", tags=["git"])
GitClient = Annotated[ServiceClient, Depends(client_dep("git"))]


@router.get("/repos")
async def list_repos(client: GitClient) -> list:
    return ServiceClient.data(await client.get("/git/repos"))


@router.get("/repos/{repo_id}")
async def get_repo(repo_id: str, client: GitClient) -> dict:
    return ServiceClient.data(await client.get(f"/git/repos/{repo_id}"))


@router.get("/repos/{repo_id}/branches")
async def list_branches(repo_id: str, client: GitClient) -> list:
    return ServiceClient.data(await client.get(f"/git/repos/{repo_id}/branches"))


@router.get("/repos/{repo_id}/commits")
async def list_commits(
    repo_id: str,
    client: GitClient,
    branch: str | None = None,
    limit: int = 30,
    cursor: str | None = None,
) -> dict:
    params: dict[str, str | int] = {"limit": limit}
    if branch:
        params["branch"] = branch
    if cursor:
        params["cursor"] = cursor
    return ServiceClient.data(
        await client.get(f"/git/repos/{repo_id}/commits", params=params)
    )


@router.get("/repos/{repo_id}/tree")
async def get_tree(
    repo_id: str, client: GitClient, ref: str = "main", path: str = ""
) -> dict:
    params = {"ref": ref, "path": path}
    response = await client.get(f"/git/repos/{repo_id}/tree", params=params)
    return ServiceClient.data(response)
