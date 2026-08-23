"""Métricas Prometheus comunes a todo servicio.

Sin esto, gestor-monitoring no tenía nada real que scrapear (ROADMAP.md
mon-03): las etiquetas `freya.metrics.port`/`freya.metrics.path` ya
existían en cada docker-compose.yml, pero ningún servicio servía
`/metrics` de verdad. `ContextMiddleware` ya mide método/ruta/estado/
duración de cada petición para el log de acceso — aquí se registra lo
mismo como métricas, sin una segunda pasada de timing.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "freya_http_requests_total",
    "Peticiones HTTP recibidas",
    ["method", "path", "status"],
)
REQUEST_DURATION = Histogram(
    "freya_http_request_duration_seconds",
    "Duración de las peticiones HTTP en segundos",
    ["method", "path"],
)


def record_request(
    method: str, path: str, status: int, duration_seconds: float
) -> None:
    REQUEST_COUNT.labels(method=method, path=path, status=str(status)).inc()
    REQUEST_DURATION.labels(method=method, path=path).observe(duration_seconds)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
