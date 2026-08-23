"""Catálogo y lectura de repositorios (docs/freya-api-contract.md §6)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from freya_common import current_tenant, require_permissions

from app.deps import ClaimsDep
from app.domain import history, repo_store
from app.domain.repos import (
    create_repo,
    delete_repo,
    get_repo,
    list_repos,
    validate_repo_name,
)
from app.models.requests import BranchCreate, RepoCreate, TagCreate

router = APIRouter(tags=["repos"], prefix="/git/repos")


async def _materialized(request: Request, repo: dict, tenant: str):
    return await repo_store.materialize(
        request.app.state.storage, tenant, repo["repo_name"], repo["default_branch"]
    )


@router.post("", status_code=201)
async def create(body: RepoCreate, claims: ClaimsDep, request: Request) -> dict:
    require_permissions(claims, "write:git")
    validate_repo_name(body.repo_name)
    tenant = current_tenant()
    client = request.app.state.gestor_db
    await repo_store.ensure_bucket(request.app.state.storage, tenant)
    repo = await create_repo(
        client,
        tenant,
        repo_name=body.repo_name,
        description=body.description,
        default_branch=body.default_branch,
        visibility=body.visibility,
        sensitive=body.sensitive,
        github_mirror_url=body.github_mirror_url,
        github_sync_enabled=body.github_sync_enabled,
        secret_validation_enabled=body.secret_validation_enabled,
    )
    # No hace falta materializar+persistir aquí: materialize() ya trata la
    # ausencia de pack/refs.json en storage como "repo vacío, sin commits
    # todavía" (ver app/domain/repo_store.py), que es exactamente el estado
    # de un repo recién creado.
    repo["clone_url"] = f"/git/{tenant}/{body.repo_name}.git"
    return repo


@router.get("")
async def list_all(claims: ClaimsDep, request: Request) -> list[dict]:
    require_permissions(claims, "read:git")
    return await list_repos(request.app.state.gestor_db, current_tenant())


@router.get("/{repo_id}")
async def get(repo_id: str, claims: ClaimsDep, request: Request) -> dict:
    require_permissions(claims, "read:git")
    return await get_repo(
        request.app.state.gestor_db, current_tenant(), repo_id=repo_id
    )


@router.delete("/{repo_id}", status_code=204)
async def remove(repo_id: str, claims: ClaimsDep, request: Request) -> None:
    require_permissions(claims, "admin:git")
    tenant = current_tenant()
    repo = await get_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    await delete_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    await repo_store.delete_from_storage(
        request.app.state.storage, tenant, repo["repo_name"]
    )


@router.get("/{repo_id}/branches")
async def branches(repo_id: str, claims: ClaimsDep, request: Request) -> list[dict]:
    require_permissions(claims, "read:git")
    tenant = current_tenant()
    repo = await get_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    workdir = await _materialized(request, repo, tenant)
    try:
        return await history.list_branches(workdir, repo["default_branch"])
    finally:
        repo_store.cleanup(workdir)


@router.post("/{repo_id}/branches", status_code=201)
async def create_branch_route(
    repo_id: str, body: BranchCreate, claims: ClaimsDep, request: Request
) -> dict:
    require_permissions(claims, "write:git")
    tenant = current_tenant()
    repo = await get_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    workdir = await _materialized(request, repo, tenant)
    try:
        await history.create_branch(
            workdir, name=body.name, from_commit=body.from_commit
        )
        await repo_store.persist(
            request.app.state.storage, tenant, repo["repo_name"], workdir
        )
    finally:
        repo_store.cleanup(workdir)
    return {"name": body.name, "from_commit": body.from_commit}


@router.delete("/{repo_id}/branches/{branch}", status_code=204)
async def delete_branch_route(
    repo_id: str, branch: str, claims: ClaimsDep, request: Request
) -> None:
    require_permissions(claims, "write:git")
    tenant = current_tenant()
    repo = await get_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    workdir = await _materialized(request, repo, tenant)
    try:
        await history.delete_branch(
            workdir, name=branch, default_branch=repo["default_branch"]
        )
        await repo_store.persist(
            request.app.state.storage, tenant, repo["repo_name"], workdir
        )
    finally:
        repo_store.cleanup(workdir)


@router.get("/{repo_id}/tags")
async def tags(repo_id: str, claims: ClaimsDep, request: Request) -> list[dict]:
    require_permissions(claims, "read:git")
    tenant = current_tenant()
    repo = await get_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    workdir = await _materialized(request, repo, tenant)
    try:
        return await history.list_tags(workdir)
    finally:
        repo_store.cleanup(workdir)


@router.post("/{repo_id}/tags", status_code=201)
async def create_tag_route(
    repo_id: str, body: TagCreate, claims: ClaimsDep, request: Request
) -> dict:
    require_permissions(claims, "write:git")
    history.validate_tag_name(body.name)
    tenant = current_tenant()
    repo = await get_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    workdir = await _materialized(request, repo, tenant)
    try:
        await history.create_tag(
            workdir,
            name=body.name,
            target_commit=body.target_commit,
            message=body.message,
            tagger_name=str(claims.get("service") or claims.get("sub") or "freya"),
            tagger_email="",
        )
        await repo_store.persist(
            request.app.state.storage, tenant, repo["repo_name"], workdir
        )
    finally:
        repo_store.cleanup(workdir)
    return {"name": body.name, "target_commit": body.target_commit}


@router.delete("/{repo_id}/tags/{tag}", status_code=204)
async def delete_tag_route(
    repo_id: str, tag: str, claims: ClaimsDep, request: Request
) -> None:
    require_permissions(claims, "write:git")
    tenant = current_tenant()
    repo = await get_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    workdir = await _materialized(request, repo, tenant)
    try:
        await history.delete_tag(workdir, name=tag)
        await repo_store.persist(
            request.app.state.storage, tenant, repo["repo_name"], workdir
        )
    finally:
        repo_store.cleanup(workdir)


@router.get("/{repo_id}/commits")
async def commits(
    repo_id: str,
    claims: ClaimsDep,
    request: Request,
    branch: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    author: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
) -> dict:
    require_permissions(claims, "read:git")
    tenant = current_tenant()
    repo = await get_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    workdir = await _materialized(request, repo, tenant)
    try:
        rows = await history.list_commits(
            workdir,
            branch=branch or repo["default_branch"],
            limit=limit,
            offset=offset,
            author=author,
            since=since,
            until=until,
        )
    finally:
        repo_store.cleanup(workdir)
    next_cursor = str(offset + limit) if len(rows) == limit else None
    return {"commits": rows, "pagination": {"limit": limit, "next_cursor": next_cursor}}


@router.get("/{repo_id}/diff")
async def diff_route(
    repo_id: str,
    claims: ClaimsDep,
    request: Request,
    base: str = Query(...),
    head: str = Query(...),
    path: str | None = Query(default=None),
) -> dict:
    require_permissions(claims, "read:git")
    tenant = current_tenant()
    repo = await get_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    workdir = await _materialized(request, repo, tenant)
    try:
        return await history.diff(workdir, base=base, head=head, path=path)
    finally:
        repo_store.cleanup(workdir)


@router.get("/{repo_id}/tree")
async def tree_route(
    repo_id: str,
    claims: ClaimsDep,
    request: Request,
    ref: str | None = Query(default=None),
    path: str = Query(default=""),
) -> list[dict]:
    """No forma parte de docs/freya-api-contract.md §6 todavía, pero
    ROADMAP.md (tarea git-04) exige árbol de ficheros navegable por API."""
    require_permissions(claims, "read:git")
    tenant = current_tenant()
    repo = await get_repo(request.app.state.gestor_db, tenant, repo_id=repo_id)
    workdir = await _materialized(request, repo, tenant)
    try:
        return await history.tree(workdir, ref=ref or repo["default_branch"], path=path)
    finally:
        repo_store.cleanup(workdir)
