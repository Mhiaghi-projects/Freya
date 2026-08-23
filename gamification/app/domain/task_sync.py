"""Sincroniza XP desde project-manager: cierra el criterio de salida de la
Fase 10 ("cerrar una task otorga XP y mueve el nivel sin intervención").

Poll periódico, no webhook -- mismo patrón que gestor-monitoring
(HealthMonitor/Scraper) y storage->gestor-monitoring (LogArchiver): no hay
bus de eventos en la plataforma, y con el volumen de tasks de este proyecto
un poll cada pocos segundos es indistinguible de "en tiempo real" para una
persona. gam_xp_events(source, source_ref) es la clave de deduplicación
real -- una task ya premiada no se vuelve a mirar aunque el poll la
encuentre otra vez en el próximo ciclo.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from freya_common import FreyaError, ServiceClient, gdb_mutate, gdb_query, new_id

from app.domain.achievements import check_and_unlock
from app.domain.stats import award_xp, get_stats

logger = logging.getLogger(__name__)

_SOURCE = "task_completed"
_XP_PER_DIFFICULTY = 15


def _xp_for_task(task: dict) -> int:
    difficulty = task.get("difficulty") or 3
    return difficulty * _XP_PER_DIFFICULTY


class TaskSyncer:
    def __init__(
        self,
        project_manager: ServiceClient,
        gestor_db: ServiceClient,
        tenant: str,
        interval_seconds: int,
    ) -> None:
        self._pm = project_manager
        self._gestor_db = gestor_db
        self._tenant = tenant
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None
        self.last_result: str = "sin ejecutar todavía"

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
                awarded = await self.sync_once()
                self.last_result = f"ok, {awarded} tasks premiadas"
            except FreyaError as exc:
                self.last_result = f"error: {exc}"
                logger.warning("fallo sincronizando XP desde project-manager: %s", exc)
            except Exception:
                self.last_result = "error inesperado"
                logger.exception("fallo inesperado sincronizando XP")
            await asyncio.sleep(self._interval)

    async def sync_once(self) -> int:
        projects = ServiceClient.data(await self._pm.get("/projects"))
        awarded = 0
        for project in projects:
            tasks = ServiceClient.data(
                await self._pm.get(
                    f"/projects/{project['id']}/tasks", params={"status": "done"}
                )
            )
            for task in tasks:
                if await self._maybe_award(task):
                    awarded += 1
        return awarded

    async def _maybe_award(self, task: dict) -> bool:
        user_id = task.get("completed_by")
        if not user_id or not user_id.startswith("usr_"):
            return False

        existing = await gdb_query(
            self._gestor_db,
            self._tenant,
            table="gam_xp_events",
            where={"source": _SOURCE, "source_ref": task["id"]},
        )
        if existing:
            return False

        xp = _xp_for_task(task)
        coins = xp
        await gdb_mutate(
            self._gestor_db,
            self._tenant,
            table="gam_xp_events",
            action="insert",
            data={
                "id": new_id("xpe"),
                "user_id": user_id,
                "source": _SOURCE,
                "source_ref": task["id"],
                "xp": xp,
                "coins": coins,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        await award_xp(
            self._gestor_db, self._tenant, user_id=user_id, xp=xp, coins=coins
        )

        completed = await gdb_query(
            self._gestor_db,
            self._tenant,
            table="gam_xp_events",
            select=["id"],
            where={"user_id": user_id, "source": _SOURCE},
            limit=200,  # tope real de gestor-db (QueryRequest.limit, le=200)
        )
        stats = await get_stats(self._gestor_db, self._tenant, user_id)
        unlocked = await check_and_unlock(
            self._gestor_db,
            self._tenant,
            user_id=user_id,
            task_count=len(completed),
            level=stats["level"],
            current_streak=stats["current_streak"],
        )
        if unlocked:
            logger.info(
                "logros desbloqueados",
                extra={"user_id": user_id, "codes": [a["code"] for a in unlocked]},
            )
        return True
