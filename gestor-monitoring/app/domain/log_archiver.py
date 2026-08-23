"""Archiva stdout/stderr de cada contenedor descubierto en storage
(ROADMAP.md mon-04, acotado): un bucket "logs" real, un objeto por
servicio y ciclo -- no monta ingesta en VictoriaLogs (LogsQL, índices,
todo lo que trae ese motor); eso sigue siendo un subsistema aparte, ver
README. El cursor por servicio (mon_log_cursors, gestor-db) evita volver
a subir lo mismo cada ciclo.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

import httpx
from freya_common import FreyaError, ServiceClient, gdb_mutate, gdb_query

from app.domain.docker_client import DockerClient

logger = logging.getLogger(__name__)

_BUCKET = "logs"


def _now_epoch() -> int:
    return int(datetime.now(UTC).timestamp())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class LogArchiver:
    def __init__(
        self,
        docker: DockerClient,
        storage: ServiceClient,
        gestor_db: ServiceClient,
        tenant: str,
        interval_seconds: int,
    ) -> None:
        self._docker = docker
        self._storage = storage
        self._gestor_db = gestor_db
        self._tenant = tenant
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._bucket_ready = False
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
                await self.archive_once()
            except Exception:
                logger.exception("fallo en el ciclo de archivado de logs")
            await asyncio.sleep(self._interval)

    async def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            await self._storage.put(
                f"/storage/buckets/{_BUCKET}", tenant=self._tenant, json={}
            )
        except FreyaError as exc:
            if exc.status_code != 409:
                raise
        self._bucket_ready = True

    async def _cursor(self, service: str) -> int:
        rows = await gdb_query(
            self._gestor_db,
            self._tenant,
            table="mon_log_cursors",
            select=["last_fetched_at"],
            where={"service": service},
            limit=1,
        )
        if not rows:
            # Primera vez: sólo desde ahora -- nunca vuelca el historial
            # entero de un contenedor que lleva días corriendo.
            return _now_epoch()
        return int(datetime.fromisoformat(rows[0]["last_fetched_at"]).timestamp())

    async def _save_cursor(self, service: str, epoch: int) -> None:
        exists = await gdb_query(
            self._gestor_db,
            self._tenant,
            table="mon_log_cursors",
            select=["service"],
            where={"service": service},
            limit=1,
        )
        data = {
            "last_fetched_at": datetime.fromtimestamp(epoch, tz=UTC).isoformat(),
            "updated_at": _now_iso(),
        }
        if exists:
            await gdb_mutate(
                self._gestor_db,
                self._tenant,
                table="mon_log_cursors",
                action="update",
                where={"service": service},
                data=data,
            )
        else:
            await gdb_mutate(
                self._gestor_db,
                self._tenant,
                table="mon_log_cursors",
                action="insert",
                data={"service": service, **data},
            )

    async def archive_once(self) -> None:
        containers = await self._docker.list_service_containers()
        running = [c for c in containers if c["state"] == "running"]
        if not running:
            return
        await self._ensure_bucket()

        cutoff = _now_epoch()
        for container in running:
            service = container["service"]
            try:
                since = await self._cursor(service)
                text = await self._docker.container_logs(container["id"], since=since)
                if text.strip():
                    key = f"{service}/{cutoff}.log"
                    await self._storage.put(
                        f"/storage/{_BUCKET}/{key}",
                        tenant=self._tenant,
                        content=text.encode("utf-8"),
                        headers={"Content-Type": "text/plain; charset=utf-8"},
                    )
                await self._save_cursor(service, cutoff)
                self.last_result[service] = "ok"
            except (FreyaError, httpx.HTTPError) as exc:
                self.last_result[service] = f"{type(exc).__name__}: {exc}"
                logger.warning("archivado de logs falló para %s: %s", service, exc)
