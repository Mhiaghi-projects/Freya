"""Protocolo git smart HTTP (docs/ARCHITECTURE.md §5).

La URL sigue la forma del `clone_url` de docs/freya-api-contract.md §6.1:
tenant y repo van en la ruta, no en X-Tenant-Context -- un cliente git real
no manda esa cabecera. La autenticación sigue siendo JWT de Freya
(Authorization: Bearer), vía `-c http.extraHeader` en el cliente git.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response
from freya_common import NotFound, require_permissions

from app.deps import ClaimsDep
from app.domain import cgi_bridge, repo_store
from app.domain.repos import get_repo_by_name
from app.domain.webhooks import trigger_pipeline_for_push

router = APIRouter(tags=["smart-http"])

_SERVICE_PERMISSION = {
    "git-upload-pack": "read:git",
    "git-receive-pack": "write:git",
}


def _remote_user(claims: dict) -> str:
    return str(claims.get("service") or claims.get("sub") or "anon")


@router.get("/git/{tenant}/{repo_name}.git/info/refs")
async def info_refs(
    tenant: str,
    repo_name: str,
    claims: ClaimsDep,
    request: Request,
    service: str = Query(...),
) -> Response:
    if service not in _SERVICE_PERMISSION:
        raise NotFound(f"Servicio git desconocido: '{service}'")
    require_permissions(claims, _SERVICE_PERMISSION[service])
    repo = await get_repo_by_name(
        request.app.state.gestor_db, tenant, repo_name=repo_name
    )

    workdir = await repo_store.materialize(
        request.app.state.storage, tenant, repo_name, repo["default_branch"]
    )
    try:
        cgi = await cgi_bridge.run_http_backend(
            project_root=workdir.parent,
            path_info=f"/{repo_name}/info/refs",
            method="GET",
            query_string=f"service={service}",
            content_type="",
            body=b"",
            remote_user=_remote_user(claims),
            git_protocol=request.headers.get("git-protocol"),
        )
    finally:
        repo_store.cleanup(workdir)
    return Response(content=cgi.body, status_code=cgi.status, headers=cgi.headers)


@router.post("/git/{tenant}/{repo_name}.git/git-upload-pack")
async def upload_pack(
    tenant: str, repo_name: str, claims: ClaimsDep, request: Request
) -> Response:
    require_permissions(claims, "read:git")
    repo = await get_repo_by_name(
        request.app.state.gestor_db, tenant, repo_name=repo_name
    )
    body = await request.body()

    workdir = await repo_store.materialize(
        request.app.state.storage, tenant, repo_name, repo["default_branch"]
    )
    try:
        cgi = await cgi_bridge.run_http_backend(
            project_root=workdir.parent,
            path_info=f"/{repo_name}/git-upload-pack",
            method="POST",
            query_string="",
            content_type="application/x-git-upload-pack-request",
            body=body,
            remote_user=_remote_user(claims),
            git_protocol=request.headers.get("git-protocol"),
        )
    finally:
        repo_store.cleanup(workdir)
    return Response(content=cgi.body, status_code=cgi.status, headers=cgi.headers)


@router.post("/git/{tenant}/{repo_name}.git/git-receive-pack")
async def receive_pack(
    tenant: str,
    repo_name: str,
    claims: ClaimsDep,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    require_permissions(claims, "write:git")
    repo = await get_repo_by_name(
        request.app.state.gestor_db, tenant, repo_name=repo_name
    )
    body = await request.body()

    workdir = await repo_store.materialize(
        request.app.state.storage, tenant, repo_name, repo["default_branch"]
    )
    try:
        cgi = await cgi_bridge.run_http_backend(
            project_root=workdir.parent,
            path_info=f"/{repo_name}/git-receive-pack",
            method="POST",
            query_string="",
            content_type="application/x-git-receive-pack-request",
            body=body,
            remote_user=_remote_user(claims),
            git_protocol=request.headers.get("git-protocol"),
        )
        # receive-pack informa de refs rechazados ("ng ... non-fast-forward")
        # dentro del cuerpo pkt-line, no como estado HTTP: lo que sí se haya
        # actualizado en el repo local es, por definición, válido — persistir
        # siempre es correcto, incluso si algún ref concreto fue rechazado.
        await repo_store.persist(request.app.state.storage, tenant, repo_name, workdir)
        # En segundo plano, después de responder al cliente git: un
        # pipeline real tarda decenas de segundos (build+lint+test+scan),
        # y `git push` no debería quedarse colgado esperando a que termine.
        background_tasks.add_task(
            trigger_pipeline_for_push,
            request.app.state.cicd,
            tenant=tenant,
            repo_name=repo_name,
        )
    finally:
        repo_store.cleanup(workdir)
    return Response(content=cgi.body, status_code=cgi.status, headers=cgi.headers)
