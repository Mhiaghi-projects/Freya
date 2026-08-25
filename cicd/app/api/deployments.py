"""Deployment Manager simulado (docs/freya-api-contract.md §8; ROADMAP.md
ci-06, recortado -- ver README)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from freya_common import current_tenant, require_service_access

from app.deps import ClaimsDep
from app.domain.deployments import create_deployment, get_deployment, list_deployments
from app.models.requests import DeploymentCreate

router = APIRouter(tags=["deployments"])


@router.post("/deployments", status_code=201)
async def create(body: DeploymentCreate, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:cicd")
    return await create_deployment(
        request.app.state.gestor_db,
        tenant,
        service=body.service,
        version_ref=body.version_ref,
        pipeline_run_id=body.pipeline_run_id,
    )


@router.get("/deployments")
async def list_all(
    claims: ClaimsDep,
    request: Request,
    service: str | None = Query(default=None),
) -> list[dict]:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:cicd")
    return await list_deployments(
        request.app.state.gestor_db, tenant, service=service
    )


@router.get("/deployments/{deployment_id}")
async def get(deployment_id: str, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:cicd")
    return await get_deployment(
        request.app.state.gestor_db, tenant, deployment_id=deployment_id
    )
