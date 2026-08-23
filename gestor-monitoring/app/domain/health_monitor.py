"""Cloud Health (ROADMAP.md mon-05): golpea /ready de cada servicio
descubierto y guarda el resultado -- el estado "ahora mismo" no basta para
calcular disponibilidad histórica (`uptime_percent_24h`,
docs/freya-api-contract.md §11.1), hace falta el historial.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from freya_common import ServiceClient, gdb_mutate, gdb_query, new_id

from app.domain.docker_client import DockerClient

logger = logging.getLogger(__name__)

_GDB_MAX_LIMIT = 200


class HealthMonitor:
    def __init__(
        self,
        docker: DockerClient,
        mesh_http: httpx.AsyncClient,
        gestor_db: ServiceClient,
        tenant: str,
        interval_seconds: int,
        timeout_seconds: float,
    ) -> None:
        self._docker = docker
        self._mesh_http = mesh_http
        self._gestor_db = gestor_db
        self._tenant = tenant
        self._interval = interval_seconds
        self._timeout = timeout_seconds
        self._task: asyncio.Task | None = None
        self.last_check: dict[str, dict[str, Any]] = {}

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _loop(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception:
                logger.exception("fallo en el ciclo de health check")
            await asyncio.sleep(self._interval)

    async def check_once(self) -> None:
        containers = await self._docker.list_service_containers()
        for container in containers:
            if not container["metrics_port"]:
                continue
            await self.check_service(
                container["service"],
                container["metrics_port"],
                scheme=container["scheme"],
            )

    async def check_service(
        self, service: str, port: str, *, scheme: str = "https"
    ) -> dict[str, Any]:
        url = f"{scheme}://freya-{service}:{port}/ready"
        started = time.perf_counter()
        error = None
        response_time_ms = None
        try:
            response = await self._mesh_http.get(url, timeout=self._timeout)
            response_time_ms = round((time.perf_counter() - started) * 1000)
            if response.status_code == 200:
                status = "healthy"
            else:
                status = "degraded"
                error = f"HTTP {response.status_code}"
        except Exception as exc:
            status = "down"
            error = f"{type(exc).__name__}: {exc}"

        result = {
            "service": service,
            "status": status,
            "response_time_ms": response_time_ms,
            "error": error,
            "checked_at": datetime.now(UTC).isoformat(),
        }
        self.last_check[service] = result

        await gdb_mutate(
            self._gestor_db,
            self._tenant,
            table="mon_health_checks",
            action="insert",
            data={
                "id": new_id("chk"),
                "service": service,
                "status": status,
                "response_time_ms": response_time_ms,
                "error": error,
            },
        )
        return result


async def uptime_percent_24h(
    client: ServiceClient, tenant: str, *, service: str
) -> float | None:
    since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await gdb_query(
            client,
            tenant,
            table="mon_health_checks",
            select=["status"],
            where={"service": service, "checked_at": {"gte": since}},
            limit=_GDB_MAX_LIMIT,
            offset=offset,
        )
        rows.extend(page)
        if len(page) < _GDB_MAX_LIMIT:
            break
        offset += _GDB_MAX_LIMIT

    if not rows:
        return None
    healthy = sum(1 for r in rows if r["status"] == "healthy")
    return round((healthy / len(rows)) * 100, 2)
