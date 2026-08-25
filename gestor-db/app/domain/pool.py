"""Conexiones a PostgreSQL, una base física por tenant (gdb-02, y la ronda
de "database por tenant, no schema por tenant" -- pedido explícito del
usuario tras discutir el aislamiento real que da cada opción).

Sin pool persistente a propósito: cada tenant es su propia base, así que
"la" conexión de turno depende de a qué tenant apunta la petición -- no
hay una base fija contra la que mantener un pool cacheado. Se abre una
conexión nueva al empezar a atender la petición y se cierra al terminar
(pedido explícito del usuario: "cada vez que consultas la base de datos
debes cerrar tu conexion"). Con `max_connections=40` en Postgres (afinado
para memoria escasa, ver services/database/docker-compose.yml), el pico
de conexiones simultáneas queda acotado por cuántas peticiones están en
vuelo a la vez, no por cuántos tenants existen.
"""

from __future__ import annotations

import asyncpg
from freya_common import DependencyUnavailable

# Base que siempre existe en cualquier servidor Postgres -- ancla para
# operaciones de catálogo (listar/crear/borrar bases) que no pueden
# correr "desde dentro" de la base que están creando o borrando.
ANCHOR_DATABASE = "postgres"


class Database:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        command_timeout: float,
    ) -> None:
        self._dsn_kwargs = dict(host=host, port=port, user=user, password=password)
        self._command_timeout = command_timeout

    async def start(self) -> None:
        """No-op a propósito: sin pool persistente no hay nada que
        arrancar en segundo plano -- cada conexión se abre y verifica su
        propio éxito o fracaso en el momento en que hace falta, no antes."""

    async def stop(self) -> None:
        """No-op a propósito: no hay pool ni conexiones en reposo que
        cerrar -- cada conexión ya se cerró sola al salir de su
        `acquire()`."""

    async def ping(self) -> str | None:
        """Comprobación de dependencia para /ready: conexión efímera
        contra la base ancla + SELECT 1. None si está bien."""
        try:
            conn = await asyncpg.connect(
                database=ANCHOR_DATABASE,
                timeout=3.0,
                **self._dsn_kwargs,
            )
        except (OSError, asyncpg.PostgresError) as exc:
            return f"{type(exc).__name__}: {exc}"
        try:
            await conn.execute("SELECT 1")
        except (OSError, asyncpg.PostgresError) as exc:
            return f"{type(exc).__name__}: {exc}"
        finally:
            await conn.close()
        return None

    def acquire(self, database: str):
        """Context manager: conexión nueva contra `database`, cerrada al
        salir. `database` es siempre explícito -- nunca hay un default
        implícito a qué base cae una petición si alguien se olvida de
        pasarlo."""
        return _OwnedConnection(self._dsn_kwargs, self._command_timeout, database)


class _OwnedConnection:
    def __init__(
        self, dsn_kwargs: dict[str, object], command_timeout: float, database: str
    ) -> None:
        self._dsn_kwargs = dsn_kwargs
        self._command_timeout = command_timeout
        self._database = database
        self._conn: asyncpg.Connection | None = None

    async def __aenter__(self) -> asyncpg.Connection:
        try:
            self._conn = await asyncpg.connect(
                database=self._database,
                command_timeout=self._command_timeout,
                **self._dsn_kwargs,
            )
        except (OSError, asyncpg.PostgresError) as exc:
            raise DependencyUnavailable(
                f"PostgreSQL no responde para la base '{self._database}': {exc}"
            ) from exc
        return self._conn

    async def __aexit__(self, *exc_info: object) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
