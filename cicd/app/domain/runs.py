"""Ejecuciones y jobs (docs/freya-api-contract.md §8; ROADMAP.md ci-03,
recortado: ver app/domain/runner.py y README para el porqué)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from freya_common import (
    FreyaError,
    NotFound,
    ServiceClient,
    UnprocessableEntity,
    gdb_mutate,
    gdb_query,
    new_id,
)

from app.domain import runner
from app.domain.pipelines import get_pipeline

_ARTIFACTS_BUCKET = "artifacts"


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _publish_artifact(
    storage: ServiceClient,
    tenant: str,
    *,
    service: str,
    run_id: str,
    wheel_b64: str,
) -> tuple[str, str, int]:
    """Decodifica el wheel (venía en base64 por stdout -- es el único modo
    de sacar un fichero de un `docker run` efímero sin montar rutas del
    host) y lo sube a storage. Devuelve (bucket, key, tamaño) para el
    registro en ci_artifacts."""
    content = base64.b64decode(wheel_b64.strip())
    try:
        await storage.put(
            f"/storage/buckets/{_ARTIFACTS_BUCKET}", tenant=tenant, json={}
        )
    except FreyaError as exc:
        if exc.status_code != 409:
            raise

    key = f"{service}/{run_id}.whl"
    headers = {"Content-Type": "application/octet-stream"}
    await storage.put(
        f"/storage/{_ARTIFACTS_BUCKET}/{key}",
        tenant=tenant,
        content=content,
        headers=headers,
    )
    # "latest" es un puntero de conveniencia (lo que instalarían los
    # demás servicios), no la fuente de verdad -- esa es la versión con
    # run_id, que nunca se sobrescribe.
    await storage.put(
        f"/storage/{_ARTIFACTS_BUCKET}/{service}/latest.whl",
        tenant=tenant,
        content=content,
        headers=headers,
    )
    return _ARTIFACTS_BUCKET, key, len(content)


async def trigger_pipeline(
    client: ServiceClient,
    tenant: str,
    storage: ServiceClient,
    *,
    pipeline_id: str,
    triggered_by: str,
    trigger_ref: str | None,
) -> dict[str, Any]:
    pipeline = await get_pipeline(client, tenant, pipeline_id=pipeline_id)

    run_id = new_id("run")
    await gdb_mutate(
        client,
        tenant,
        table="ci_runs",
        action="insert",
        data={
            "id": run_id,
            "pipeline_id": pipeline_id,
            "status": "running",
            "triggered_by": triggered_by,
            "trigger_ref": trigger_ref,
            "started_at": _now(),
        },
    )

    try:
        result = await runner.run_standard_tests(pipeline["service"])
    except runner.InvalidServiceError as exc:
        await gdb_mutate(
            client,
            tenant,
            table="ci_runs",
            action="update",
            where={"id": run_id},
            data={"status": "failed", "finished_at": _now()},
        )
        raise NotFound(str(exc)) from exc
    except runner.InvalidPipelineSpecError as exc:
        await gdb_mutate(
            client,
            tenant,
            table="ci_runs",
            action="update",
            where={"id": run_id},
            data={"status": "failed", "finished_at": _now()},
        )
        raise UnprocessableEntity(str(exc)) from exc

    for job in result.jobs:
        job_id = new_id("job")
        # una imagen rota puede vomitar MBs; el wheel en base64 también
        # puede pasarse de esto, pero se decodifica ANTES de truncar
        # (abajo), nunca desde esta copia recortada.
        log = job.log[-20000:]

        await gdb_mutate(
            client,
            tenant,
            table="ci_jobs",
            action="insert",
            data={
                "id": job_id,
                "run_id": run_id,
                "name": job.name,
                "status": "success" if job.exit_code == 0 else "failed",
                "exit_code": job.exit_code,
                "log": log,
                "started_at": _now(),
                "finished_at": _now(),
            },
        )

        if job.name == "build_artifact" and job.exit_code == 0:
            # ci_artifacts.job_id referencia esta fila, así que sólo puede
            # insertarse DESPUÉS de que exista -- el log real (el wheel
            # entero en base64) ya se guardó arriba, aquí se reemplaza por
            # un mensaje corto una vez subido a storage.
            try:
                bucket, key, size = await _publish_artifact(
                    storage,
                    tenant,
                    service=pipeline["service"],
                    run_id=run_id,
                    wheel_b64=job.log,
                )
                await gdb_mutate(
                    client,
                    tenant,
                    table="ci_artifacts",
                    action="insert",
                    data={
                        "id": new_id("art"),
                        "run_id": run_id,
                        "job_id": job_id,
                        "storage_bucket": bucket,
                        "storage_key": key,
                    },
                )
                await gdb_mutate(
                    client,
                    tenant,
                    table="ci_jobs",
                    action="update",
                    where={"id": job_id},
                    data={"log": f"artefacto publicado: {bucket}/{key} ({size} bytes)"},
                )
            except Exception as exc:  # noqa: BLE001 - se refleja como fallo del job, no se pierde en silencio
                await gdb_mutate(
                    client,
                    tenant,
                    table="ci_jobs",
                    action="update",
                    where={"id": job_id},
                    data={
                        "status": "failed",
                        "exit_code": 1,
                        "log": f"fallo publicando el artefacto: {exc}",
                    },
                )
                result.success = False

    await gdb_mutate(
        client,
        tenant,
        table="ci_runs",
        action="update",
        where={"id": run_id},
        data={
            "status": "success" if result.success else "failed",
            "finished_at": _now(),
        },
    )

    return await get_run(client, tenant, run_id=run_id)


async def get_run(
    client: ServiceClient, tenant: str, *, run_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="ci_runs",
        select=[
            "id",
            "pipeline_id",
            "status",
            "triggered_by",
            "trigger_ref",
            "started_at",
            "finished_at",
            "created_at",
        ],
        where={"id": run_id},
        limit=1,
    )
    if not rows:
        raise NotFound(
            f"La ejecución '{run_id}' no existe", details={"run_id": run_id}
        )
    run = rows[0]
    run["jobs"] = await list_jobs(client, tenant, run_id=run_id)
    return run


async def list_runs(
    client: ServiceClient, tenant: str, *, pipeline_id: str
) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="ci_runs",
        select=[
            "id",
            "status",
            "triggered_by",
            "trigger_ref",
            "started_at",
            "finished_at",
        ],
        where={"pipeline_id": pipeline_id},
        order_by=[{"field": "created_at", "direction": "desc"}],
        limit=200,
    )


async def list_jobs(
    client: ServiceClient, tenant: str, *, run_id: str
) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="ci_jobs",
        select=["id", "name", "status", "exit_code", "started_at", "finished_at"],
        where={"run_id": run_id},
        order_by=[{"field": "started_at", "direction": "asc"}],
        limit=50,
    )


async def get_job_log(
    client: ServiceClient, tenant: str, *, job_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client,
        tenant,
        table="ci_jobs",
        select=["id", "run_id", "name", "status", "exit_code", "log"],
        where={"id": job_id},
        limit=1,
    )
    if not rows:
        raise NotFound(f"El job '{job_id}' no existe", details={"job_id": job_id})
    return rows[0]
