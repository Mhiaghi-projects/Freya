"""Vista de cicd (docs/ROADMAP.md Fase 9, punto 5): proxy delgado sobre
cicd/app/api/{pipelines,deployments}.py."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from freya_common import ServiceClient

from app.infra.gateway import client_dep

router = APIRouter(prefix="/api/cicd", tags=["cicd"])
CicdClient = Annotated[ServiceClient, Depends(client_dep("cicd"))]


def _tenant(project: str | None) -> str:
    return project or "freya"


@router.get("/pipelines")
async def list_pipelines(client: CicdClient, project: str | None = None) -> list:
    return ServiceClient.data(await client.get("/pipelines", tenant=_tenant(project)))


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(
    pipeline_id: str, client: CicdClient, project: str | None = None
) -> dict:
    return ServiceClient.data(
        await client.get(f"/pipelines/{pipeline_id}", tenant=_tenant(project))
    )


@router.get("/pipelines/{pipeline_id}/runs")
async def list_runs(
    pipeline_id: str, client: CicdClient, limit: int = 20, project: str | None = None
) -> list:
    return ServiceClient.data(
        await client.get(
            f"/pipelines/{pipeline_id}/runs",
            params={"limit": limit},
            tenant=_tenant(project),
        )
    )


@router.post("/pipelines/{pipeline_id}/trigger", status_code=201)
async def trigger_pipeline(
    pipeline_id: str, client: CicdClient, project: str | None = None
) -> dict:
    # cicd exige un cuerpo (TriggerRequest), aunque todos sus campos tengan
    # default -- sin json={} aquí, la petición nunca llevaba Content-Type
    # ni cuerpo alguno y cicd la rechazaba con 422 (bug real, preexistente:
    # el botón "Disparar pipeline" del panel estaba roto para cualquier
    # pipeline, encontrado al integrar este cambio con el CI/CD propio).
    return ServiceClient.data(
        await client.post(
            f"/pipelines/{pipeline_id}/trigger", json={}, tenant=_tenant(project)
        )
    )


@router.get("/runs/{run_id}")
async def get_run(run_id: str, client: CicdClient, project: str | None = None) -> dict:
    return ServiceClient.data(
        await client.get(f"/runs/{run_id}", tenant=_tenant(project))
    )


@router.get("/jobs/{job_id}/log")
async def get_job_log(
    job_id: str, client: CicdClient, project: str | None = None
) -> dict:
    return ServiceClient.data(
        await client.get(f"/jobs/{job_id}/log", tenant=_tenant(project))
    )
