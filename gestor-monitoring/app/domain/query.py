"""Proxy de consultas PromQL contra VictoriaMetrics
(docs/freya-api-contract.md §11.2).

Un puñado de nombres de métrica "amigables" se traducen a PromQL real
usando las series que expone `freya_common.metrics` (las mismas que
`app/domain/scraper.py` importa). Cualquier otro valor de `metric` se
trata como una expresión PromQL cruda -- es la vía de escape que hace que
esto sea "consultable por PromQL" de verdad, no sólo los atajos previstos
aquí.
"""

from __future__ import annotations

from typing import Any

import httpx
from freya_common import BadRequest, DependencyUnavailable

_FRIENDLY_METRICS = {
    "request_rate": 'sum(rate(freya_http_requests_total{{service="{service}"}}[5m]))',
    "error_rate": (
        'sum(rate(freya_http_requests_total{{service="{service}",status=~"5.."}}[5m])) '
        '/ sum(rate(freya_http_requests_total{{service="{service}"}}[5m])) * 100'
    ),
    "response_time_ms": (
        "histogram_quantile(0.95, sum(rate("
        'freya_http_request_duration_seconds_bucket{{service="{service}"}}[5m])) '
        "by (le)) * 1000"
    ),
}

_RESOLUTION_SECONDS = {"1m": 60, "5m": 300, "1h": 3600, "1d": 86400}


def build_promql(metric: str, service: str) -> str:
    template = _FRIENDLY_METRICS.get(metric)
    if template:
        return template.format(service=service)
    return metric


async def query_range(
    http: httpx.AsyncClient,
    metrics_url: str,
    *,
    promql: str,
    start: int,
    end: int,
    resolution: str,
) -> list[dict[str, Any]]:
    step = _RESOLUTION_SECONDS.get(resolution, 300)
    try:
        response = await http.get(
            f"{metrics_url.rstrip('/')}/api/v1/query_range",
            params={"query": promql, "start": start, "end": end, "step": step},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise DependencyUnavailable(f"metrics no responde: {exc}") from exc

    if response.status_code == 400:
        raise BadRequest(f"consulta PromQL inválida: {response.text}")
    response.raise_for_status()

    result = response.json().get("data", {}).get("result", [])
    if not result:
        return []
    # Una única serie (build_promql ya la agrega/filtra por servicio): la
    # primera es la que importa.
    return [
        {"timestamp": int(ts), "value": float(value)}
        for ts, value in result[0].get("values", [])
    ]
