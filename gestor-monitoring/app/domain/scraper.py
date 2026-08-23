"""Scrape periódico de /metrics de cada servicio descubierto, reenviado tal
cual a VictoriaMetrics (ROADMAP.md mon-03). No se parsea ni se reinterpreta
el texto Prometheus -- VictoriaMetrics ya sabe leerlo por su cuenta vía
`/api/v1/import/prometheus`; sólo se añade la etiqueta "service" (por
`extra_label`) para poder diferenciar el origen en las consultas, ya que
`freya_common.metrics` no la incluye (cada proceso sólo conoce su propio
nombre a través de este import, no de sus propias métricas).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx

from app.domain.docker_client import DockerClient

logger = logging.getLogger(__name__)


class Scraper:
    def __init__(
        self,
        docker: DockerClient,
        mesh_http: httpx.AsyncClient,
        metrics_url: str,
        interval_seconds: int,
        timeout_seconds: float,
    ) -> None:
        self._docker = docker
        self._mesh_http = mesh_http
        self._metrics_url = metrics_url.rstrip("/")
        self._interval = interval_seconds
        self._timeout = timeout_seconds
        self._task: asyncio.Task | None = None
        self.last_result: dict[str, str] = {}

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
                await self.scrape_once()
            except Exception:
                logger.exception("fallo en el ciclo de scrape de métricas")
            await asyncio.sleep(self._interval)

    async def scrape_once(self) -> None:
        containers = await self._docker.list_service_containers()
        for container in containers:
            if container["state"] != "running" or not container["metrics_port"]:
                continue
            service = container["service"]
            try:
                text = await self._fetch(
                    service,
                    container["metrics_port"],
                    container["metrics_path"],
                    scheme=container["scheme"],
                )
                await self._import(service, text)
                self.last_result[service] = "ok"
            except Exception as exc:
                self.last_result[service] = f"{type(exc).__name__}: {exc}"
                logger.warning("scrape de métricas falló para %s: %s", service, exc)

    async def _fetch(
        self, service: str, port: str, path: str, *, scheme: str = "https"
    ) -> str:
        url = f"{scheme}://freya-{service}:{port}{path}"
        response = await self._mesh_http.get(url, timeout=self._timeout)
        response.raise_for_status()
        return response.text

    async def _import(self, service: str, text: str) -> None:
        if not text.strip():
            return
        response = await self._mesh_http.post(
            f"{self._metrics_url}/api/v1/import/prometheus",
            params={"extra_label": f"service={service}"},
            content=text.encode("utf-8"),
            timeout=self._timeout,
        )
        response.raise_for_status()
