"""Deployment Manager, sólo el modelo (ROADMAP.md ci-06, recortado: decidido
en vivo con el usuario, ver README). Nunca toca otro contenedor -- ni
siquiera el propio: crear un registro de despliegue exige que la
ejecución que lo respalda haya sido un éxito ("antes de ejecutar algo debe
correr con un pipeline; si falla, no se ejecuta"), y el estado que queda
grabado es siempre `simulated`, nunca `deployed`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freya_common import (
    Conflict,
    NotFound,
    ServiceClient,
    gdb_mutate,
    gdb_query,
    new_id,
)

from app.domain.runs import get_run


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_deployment(
    client: ServiceClient,
    tenant: str,
    *,
    service: str,
    version_ref: str,
    pipeline_run_id: str,
) -> dict[str, Any]:
    run = await get_run(client, tenant, run_id=pipeline_run_id)
    if run["status"] != "success":
        raise Conflict(
            f"La ejecución '{pipeline_run_id}' no fue un éxito "
            f"(status={run['status']}): no se puede desplegar sobre ella",
            details={"pipeline_run_id": pipeline_run_id, "run_status": run["status"]},
        )

    deployment_id = new_id("dep")
    await gdb_mutate(
        client,
        tenant,
        table="ci_deployments",
        action="insert",
        data={
            "id": deployment_id,
            "service": service,
            "version_ref": version_ref,
            "status": "simulated",
            "pipeline_run_id": pipeline_run_id,
        },
    )
    return {
        "deployment_id": deployment_id,
        "service": service,
        "version_ref": version_ref,
        "status": "simulated",
        "note": (
            "Deployment Manager simulado: este registro no desplegó nada de "
            "verdad. Ver cicd/README.md, sección Pendiente."
        ),
        "created_at": _now(),
    }


async def get_deployment(
    client: ServiceClient, tenant: str, *, deployment_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="ci_deployments",
        select=[
            "id",
            "service",
            "version_ref",
            "status",
            "pipeline_run_id",
            "created_at",
        ],
        where={"id": deployment_id},
        limit=1,
    )
    if not rows:
        raise NotFound(
            f"El despliegue '{deployment_id}' no existe",
            details={"deployment_id": deployment_id},
        )
    return rows[0]


async def list_deployments(
    client: ServiceClient, tenant: str, *, service: str | None
) -> list[dict[str, Any]]:
    where: dict[str, Any] = {}
    if service:
        where["service"] = service
    return await gdb_query(
        client,
        tenant,
        table="ci_deployments",
        select=[
            "id",
            "service",
            "version_ref",
            "status",
            "pipeline_run_id",
            "created_at",
        ],
        where=where,
        order_by=[{"field": "created_at", "direction": "desc"}],
        limit=200,
    )
