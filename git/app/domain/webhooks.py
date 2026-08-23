"""Dispara el pipeline standard-tests del servicio homónimo tras un push
que ya se persistió con éxito (ROADMAP.md ci-04/git-08, respuesta del
usuario en Fase 8: "antes de ejecutar algo debe correr con un pipeline").

Mejor esfuerzo, siempre en segundo plano (ver smart_http.py,
BackgroundTasks): si `cicd` no tiene un pipeline `<repo>-standard-tests`,
o no responde, el push ya se completó igual -- un fallo aquí nunca debe
poder tumbar ni retrasar la respuesta al cliente git real.
"""

from __future__ import annotations

import logging

from freya_common import FreyaError, ServiceClient

logger = logging.getLogger(__name__)


async def trigger_pipeline_for_push(
    cicd: ServiceClient, *, tenant: str, repo_name: str
) -> None:
    pipeline_name = f"{repo_name}-standard-tests"
    try:
        response = await cicd.get("/pipelines", tenant=tenant)
        pipelines = ServiceClient.data(response)
        pipeline = next((p for p in pipelines if p["name"] == pipeline_name), None)
        if pipeline is None:
            # Sin pipeline homónimo -- la mayoría de repos no tienen uno,
            # no es una condición de error.
            return

        await cicd.post(
            f"/pipelines/{pipeline['id']}/trigger",
            tenant=tenant,
            json={"triggered_by": "push", "trigger_ref": repo_name},
            timeout=200.0,
        )
        logger.info("pipeline disparado tras push", extra={"repo": repo_name})
    except FreyaError as exc:
        logger.warning(
            "no se pudo disparar el pipeline tras el push (el push ya se completó)",
            extra={"repo": repo_name, "error": str(exc)},
        )
