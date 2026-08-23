"""Aplica migrations/*.sql contra gestor-db, con reintento en segundo plano.

Mismo patrón que el pool de gestor-db: si gestor-db no está listo todavía al
arrancar, el servicio no se cae — reintenta con backoff, y /ready lo
refleja. Cualquier servicio con schema propio lo usa igual.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from .errors import FreyaError
from .http import ServiceClient

logger = logging.getLogger(__name__)

_INITIAL_RETRY_SECONDS = 1.0
_MAX_RETRY_SECONDS = 30.0


def load_migrations(directory: Path) -> list[dict[str, str]]:
    files = sorted(directory.glob("*.sql"))
    return [{"filename": f.name, "sql": f.read_text(encoding="utf-8")} for f in files]


class MigrationRunner:
    def __init__(
        self, client: ServiceClient, *, tenant: str, migrations_dir: Path
    ) -> None:
        self._client = client
        self._tenant = tenant
        self._migrations = load_migrations(migrations_dir)
        self._done = False
        self._task: asyncio.Task | None = None

    @property
    def done(self) -> bool:
        return self._done

    def start(self) -> None:
        if self._migrations:
            self._task = asyncio.create_task(self._run_with_retry())
        else:
            self._done = True

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run_with_retry(self) -> None:
        delay = _INITIAL_RETRY_SECONDS
        while not self._done:
            try:
                await self._client.post(
                    "/migrations",
                    tenant=self._tenant,
                    json={"schema": self._tenant, "migrations": self._migrations},
                )
                self._done = True
                logger.info(
                    "migraciones aplicadas", extra={"count": len(self._migrations)}
                )
                return
            except FreyaError as exc:
                logger.warning(
                    "no se pudieron aplicar las migraciones, reintentando",
                    extra={"error": str(exc), "retry_in_seconds": delay},
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RETRY_SECONDS)

    async def ping(self) -> str | None:
        return None if self._done else "migraciones aún no aplicadas"
