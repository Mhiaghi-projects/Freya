"""Pipelines y ejecuciones (docs/freya-api-contract.md §8, recortado)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant, require_service_access

from app.deps import ClaimsDep
from app.domain.pipelines import create_pipeline, get_pipeline, list_pipelines
from app.domain.runs import get_job_log, get_run, list_runs, trigger_pipeline
from app.models.requests import PipelineCreate, TriggerRequest

router = APIRouter(tags=["pipelines"])


@router.post("/pipelines", status_code=201)
async def create(body: PipelineCreate, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:cicd")
    return await create_pipeline(
        request.app.state.gestor_db,
        tenant,
        name=body.name,
        service=body.service,
        pipeline_type=body.pipeline_type,
    )


@router.get("/pipelines")
async def list_all(claims: ClaimsDep, request: Request) -> list[dict]:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:cicd")
    return await list_pipelines(request.app.state.gestor_db, tenant)


@router.get("/pipelines/{pipeline_id}")
async def get(pipeline_id: str, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:cicd")
    return await get_pipeline(
        request.app.state.gestor_db, tenant, pipeline_id=pipeline_id
    )


@router.post("/pipelines/{pipeline_id}/trigger", status_code=201)
async def trigger(
    pipeline_id: str, body: TriggerRequest, claims: ClaimsDep, request: Request
) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:cicd")
    return await trigger_pipeline(
        request.app.state.gestor_db,
        tenant,
        request.app.state.storage,
        pipeline_id=pipeline_id,
        triggered_by=body.triggered_by,
        trigger_ref=body.trigger_ref,
    )


@router.get("/pipelines/{pipeline_id}/runs")
async def runs(pipeline_id: str, claims: ClaimsDep, request: Request) -> list[dict]:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:cicd")
    return await list_runs(
        request.app.state.gestor_db, tenant, pipeline_id=pipeline_id
    )


@router.get("/runs/{run_id}")
async def run_detail(run_id: str, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:cicd")
    return await get_run(request.app.state.gestor_db, tenant, run_id=run_id)


@router.get("/jobs/{job_id}/log")
async def job_log(job_id: str, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:cicd")
    return await get_job_log(
        request.app.state.gestor_db, tenant, job_id=job_id
    )
