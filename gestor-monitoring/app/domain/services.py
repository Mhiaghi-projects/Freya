"""Vista agregada de servicios para Cloud Health
(docs/freya-api-contract.md §11.1, §11.5)."""

from __future__ import annotations

from typing import Any

from freya_common import NotFound, ServiceClient

from app.domain.docker_client import DockerClient
from app.domain.health_monitor import HealthMonitor, uptime_percent_24h

_DEFAULT_CHECK = {
    "status": "unknown",
    "response_time_ms": None,
    "error": None,
    "checked_at": None,
}


async def list_services(
    docker: DockerClient,
    monitor: HealthMonitor,
    gestor_db: ServiceClient,
    tenant: str,
) -> dict[str, Any]:
    containers = await docker.list_service_containers()
    services = []
    counts = {"healthy": 0, "degraded": 0, "down": 0, "unknown": 0}

    for container in containers:
        if not container["metrics_port"]:
            continue
        name = container["service"]
        last = monitor.last_check.get(name, _DEFAULT_CHECK)
        uptime = await uptime_percent_24h(gestor_db, tenant, service=name)
        counts[last["status"]] = counts.get(last["status"], 0) + 1
        services.append(
            {
                "service": name,
                "status": last["status"],
                "uptime_percent_24h": uptime,
                "response_time_ms": last.get("response_time_ms"),
                "last_check": last.get("checked_at"),
            }
        )

    overall = "healthy"
    if counts["down"]:
        overall = "down"
    elif counts["degraded"] or counts["unknown"]:
        overall = "degraded"

    return {
        "overall_status": overall,
        "services": sorted(services, key=lambda s: s["service"]),
        "summary": {"total": len(services), **counts},
    }


async def get_service(
    docker: DockerClient,
    monitor: HealthMonitor,
    gestor_db: ServiceClient,
    tenant: str,
    *,
    service: str,
) -> dict[str, Any]:
    containers = await docker.list_service_containers()
    match = next((c for c in containers if c["service"] == service), None)
    if match is None:
        raise NotFound(
            f"'{service}' no es un servicio conocido", details={"service": service}
        )
    last = monitor.last_check.get(service, _DEFAULT_CHECK)
    uptime = await uptime_percent_24h(gestor_db, tenant, service=service)
    return {
        "service": service,
        "status": last["status"],
        "response_time_ms": last.get("response_time_ms"),
        "error": last.get("error"),
        "uptime_percent_24h": uptime,
        "image": match["image"],
        "container_status": match["status"],
    }
