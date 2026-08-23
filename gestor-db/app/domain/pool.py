"""Pool de conexiones a PostgreSQL (gdb-02).

La conexión inicial se intenta en segundo plano con reintento y backoff: si
`database` no está arriba todavía (o cae y vuelve), el proceso no se cae con
ella, y /ready lo refleja como no listo hasta que el pool exista. Una vez
creado, asyncpg reconecta conexiones individuales caídas de forma
transparente en el siguiente `acquire()`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import asyncpg
from freya_common import DependencyUnavailable

from app.domain.tenant import quote_identifier

logger = logging.getLogger(__name__)

_INITIAL_RETRY_SECONDS = 1.0
_MAX_RETRY_SECONDS = 30.0


class Database:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        min_size: int,
        max_size: int,
        command_timeout: float,
    ) -> None:
        self._dsn_kwargs = dict(
            host=host, port=port, database=database, user=user, password=password
        )
        self._min_size = min_size
        self._max_size = max_size
        self._command_timeout = command_timeout
        self._pool: asyncpg.Pool | None = None
        self._connect_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._connect_task = asyncio.create_task(self._connect_with_retry())

    async def stop(self) -> None:
        if self._connect_task is not None:
            self._connect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._connect_task
            self._connect_task = None
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _connect_with_retry(self) -> None:
        delay = _INITIAL_RETRY_SECONDS
        while True:
            try:
                self._pool = await asyncpg.create_pool(
                    min_size=self._min_size,
                    max_size=self._max_size,
                    command_timeout=self._command_timeout,
                    **self._dsn_kwargs,
                )
                logger.info(
                    "pool de PostgreSQL listo",
                    extra={"min_size": self._min_size, "max_size": self._max_size},
                )
                return
            except (OSError, asyncpg.PostgresError) as exc:
                logger.warning(
                    "no se pudo conectar a PostgreSQL, reintentando",
                    extra={"error": str(exc), "retry_in_seconds": delay},
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RETRY_SECONDS)

    async def ping(self) -> str | None:
        """Comprobación de dependencia para /ready. None si está bien."""
        if self._pool is None:
            return "el pool aún no se ha conectado a PostgreSQL"
        try:
            async with self._pool.acquire(timeout=3.0) as conn:
                await conn.execute("SELECT 1")
            return None
        except Exception as exc:  # una base caída no debe tumbar el proceso
            return f"{type(exc).__name__}: {exc}"

    def acquire(self, *, schema: str | None = None):
        """Context manager: conexión del pool, con search_path fijado."""
        if self._pool is None:
            raise DependencyUnavailable("PostgreSQL no está disponible todavía")
        return _ScopedConnection(self._pool, schema)


class _ScopedConnection:
    """Adquiere una conexión y le fija el search_path al schema del tenant.

    SET search_path no admite parámetros ligados: el nombre ya viene validado
    por resolve_schema, así que sólo hace falta citarlo.
    """

    def __init__(self, pool: asyncpg.Pool, schema: str | None) -> None:
        self._pool = pool
        self._schema = schema
        self._conn: asyncpg.pool.PoolConnectionProxy | None = None

    async def __aenter__(self) -> asyncpg.pool.PoolConnectionProxy:
        self._conn = await self._pool.acquire()
        # Siempre se fija, incluso a "public": una conexión reciclada del
        # pool puede traer el search_path de un tenant anterior.
        target = (
            f"{quote_identifier(self._schema)}, public"
            if self._schema is not None
            else "public"
        )
        await self._conn.execute(f"SET search_path TO {target}")
        return self._conn

    async def __aexit__(self, *exc_info: object) -> None:
        if self._conn is not None:
            await self._pool.release(self._conn)
            self._conn = None
