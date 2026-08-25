"""Motor de migraciones SQL versionadas (gdb-06).

Cada servicio manda el contenido de sus migrations/NNNN_*.sql; gestor-db es
el único que las ejecuta, porque es el único que toca PostgreSQL directo.

Una base de datos es de un tenant, no de un servicio (docs/freya-api-
contract.md §4) -- varios servicios comparten la misma base, en tablas
distintas. Se registran en public.freya_migrations, dentro de la propia
base del tenant, por (service, filename): ya no hace falta una columna
"schema_name" (antes en una tabla compartida entre todos los tenants,
public.freya_schema_migrations) porque ahora cada base sólo tiene sus
propias filas -- borrar el tenant (DROP DATABASE) se lleva su bookkeeping
solo, sin un DELETE aparte. Reejecutar con el mismo contenido no hace
nada; con contenido distinto para un fichero ya aplicado es un conflicto.
"""

from __future__ import annotations

import hashlib

from freya_common import Conflict

from app.domain.pool import ANCHOR_DATABASE, Database
from app.domain.tenant import quote_identifier

_TRACKING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.freya_migrations (
    service text NOT NULL,
    filename text NOT NULL,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (service, filename)
)
"""


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


async def ensure_database(db: Database, name: str) -> bool:
    """CREATE DATABASE si no existe -- idempotente por chequeo explícito
    (Postgres no tiene "CREATE DATABASE IF NOT EXISTS"). Corre contra la
    base ancla: no se puede crear una base "desde dentro" de sí misma, y
    tampoco dentro de una transacción (Postgres lo prohíbe para CREATE
    DATABASE) -- por eso conn.execute() suelto, nunca conn.transaction().
    Devuelve True si la creó, False si ya existía."""
    async with db.acquire(ANCHOR_DATABASE) as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", name
        )
        if exists:
            return False
        await conn.execute(f"CREATE DATABASE {quote_identifier(name)}")
        return True


async def apply_migrations(
    db: Database,
    *,
    database: str,
    service: str,
    migrations: list[tuple[str, str]],
) -> dict[str, list[str]]:
    """Aplica migraciones (filename, sql) en orden. Devuelve applied/skipped.

    Se asegura la base sola (no depende de que quien la llame ya la haya
    creado) -- así el fan-out de aprovisionamiento de un tenant nuevo
    (frontend/app/api/admin.py:create_tenant, que llama a gestor-db y a
    storage/git/cicd/project-manager por separado) no depende de en qué
    orden lleguen esas llamadas."""
    await ensure_database(db, database)
    applied: list[str] = []
    skipped: list[str] = []

    async with db.acquire(database) as conn:
        await conn.execute(_TRACKING_TABLE_SQL)

        for filename, sql in sorted(migrations, key=lambda item: item[0]):
            checksum = _checksum(sql)
            existing = await conn.fetchval(
                """
                SELECT checksum FROM public.freya_migrations
                WHERE service = $1 AND filename = $2
                """,
                service,
                filename,
            )

            if existing is not None:
                if existing != checksum:
                    raise Conflict(
                        f"La migración '{filename}' ya se aplicó con otro contenido",
                        details={
                            "filename": filename,
                            "database": database,
                            "service": service,
                        },
                    )
                skipped.append(filename)
                continue

            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    """
                    INSERT INTO public.freya_migrations
                        (service, filename, checksum)
                    VALUES ($1, $2, $3)
                    """,
                    service,
                    filename,
                    checksum,
                )
            applied.append(filename)

    return {"database": database, "applied": applied, "skipped": skipped}
