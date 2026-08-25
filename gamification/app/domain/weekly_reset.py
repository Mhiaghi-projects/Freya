"""Reinicio semanal del leaderboard (pedido explícito del usuario:
"resetear el nivel cada semana y ponerlo en el leaderboard"). total_xp y
level (progreso de logros/streak) nunca se tocan aquí -- weekly_xp es
aparte, lo que compite semana a semana. Antes de resetear, guarda una foto
del ranking de la semana que termina -- si no, "quién ganó esta semana" se
perdería en el instante mismo del reset. Mismo patrón de poll periódico
que TaskSyncer (sin bus de eventos en la plataforma)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, date, datetime, timedelta

from freya_common import FreyaError, ServiceClient, gdb_mutate, gdb_query, new_id

logger = logging.getLogger(__name__)

_STATE_ID = "singleton"


def _week_start(d: date) -> date:
    """Lunes de la semana ISO de `d`."""
    return d - timedelta(days=d.weekday())


class WeeklyResetter:
    def __init__(
        self, gestor_db: ServiceClient, tenant: str, interval_seconds: int
    ) -> None:
        self._gestor_db = gestor_db
        self._tenant = tenant
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None
        self.last_result = "sin ejecutar todavía"

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
                reset = await self.check_and_reset_once()
                self.last_result = "reseteado" if reset else "sin cambios"
            except FreyaError as exc:
                self.last_result = f"error: {exc}"
                logger.warning("fallo revisando el reset semanal: %s", exc)
            except Exception:
                self.last_result = "error inesperado"
                logger.exception("fallo inesperado revisando el reset semanal")
            await asyncio.sleep(self._interval)

    async def check_and_reset_once(self) -> bool:
        current_week = _week_start(datetime.now(UTC).date())

        rows = await gdb_query(
            self._gestor_db,
            self._tenant,
            table="gam_weekly_reset_state",
            where={"id": _STATE_ID},
        )
        last_week = (
            date.fromisoformat(str(rows[0]["last_reset_week_start"]))
            if rows and rows[0]["last_reset_week_start"]
            else None
        )
        if last_week == current_week:
            return False

        if last_week is not None:
            await self._snapshot(last_week)

        # "gte": 0 en vez de un where vacío -- gestor-db rechaza un
        # update/delete sin condición (protección real, no hay forma de
        # "resetear todos" salvo una condición que de hecho case con todos.
        await gdb_mutate(
            self._gestor_db,
            self._tenant,
            table="gam_user_stats",
            action="update",
            where={"weekly_xp": {"gte": 0}},
            data={"weekly_xp": 0, "weekly_coins": 0},
        )

        state_data = {
            "id": _STATE_ID, "last_reset_week_start": current_week.isoformat()
        }
        if rows:
            await gdb_mutate(
                self._gestor_db,
                self._tenant,
                table="gam_weekly_reset_state",
                action="update",
                where={"id": _STATE_ID},
                data={"last_reset_week_start": current_week.isoformat()},
            )
        else:
            await gdb_mutate(
                self._gestor_db,
                self._tenant,
                table="gam_weekly_reset_state",
                action="insert",
                data=state_data,
            )
        logger.info(
            "leaderboard semanal reseteado",
            extra={"week_start": current_week.isoformat()},
        )
        return True

    async def _snapshot(self, week_start: date) -> None:
        standings = await gdb_query(
            self._gestor_db,
            self._tenant,
            table="gam_user_stats",
            select=["user_id", "weekly_xp"],
            where={"weekly_xp": {"gt": 0}},
            order_by=[{"field": "weekly_xp", "direction": "desc"}],
            limit=200,
        )
        for i, row in enumerate(standings):
            await gdb_mutate(
                self._gestor_db,
                self._tenant,
                table="gam_weekly_leaderboard_snapshots",
                action="insert",
                data={
                    "id": new_id("wls"),
                    "week_start": week_start.isoformat(),
                    "user_id": row["user_id"],
                    "weekly_xp": row["weekly_xp"],
                    "rank": i + 1,
                },
            )
