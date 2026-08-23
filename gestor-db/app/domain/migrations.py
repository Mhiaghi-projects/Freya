"""Motor de migraciones SQL versionadas (gdb-06).

Cada servicio manda el contenido de sus migrations/NNNN_*.sql; gestor-db es
el único que las ejecuta, porque es el único que toca PostgreSQL directo.

Un schema es de un tenant, no de un servicio (docs/freya-api-contract.md
§4) — varios servicios comparten el mismo schema, en tablas distintas. Se
registran en public.freya_schema_migrations por (schema, service, filename):
el schema fija dónde se aplica, el servicio desambigua migraciones de
distintos servicios con el mismo nombre de fichero. Reejecutar con el mismo
contenido no hace nada; con contenido distinto para un fichero ya aplicado
es un conflicto.
"""

from __future__ import annotations

import hashlib

from freya_common import Conflict

from app.domain.pool import Database
from app.domain.tenant import quote_identifier

_TRACKING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.freya_schema_migrations (
    schema_name text NOT NULL,
    service text NOT NULL,
    filename text NOT NULL,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (schema_name, service, filename)
)
"""


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


async def apply_migrations(
    db: Database,
    *,
    schema: str,
    service: str,
    migrations: list[tuple[str, str]],
) -> dict[str, list[str]]:
    """Aplica migraciones (filename, sql) en orden. Devuelve applied/skipped."""
    applied: list[str] = []
    skipped: list[str] = []

    async with db.acquire() as conn:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(schema)}")
        await conn.execute(_TRACKING_TABLE_SQL)

        for filename, sql in sorted(migrations, key=lambda item: item[0]):
            checksum = _checksum(sql)
            existing = await conn.fetchval(
                """
                SELECT checksum FROM public.freya_schema_migrations
                WHERE schema_name = $1 AND service = $2 AND filename = $3
                """,
                schema,
                service,
                filename,
            )

            if existing is not None:
                if existing != checksum:
                    raise Conflict(
                        f"La migración '{filename}' ya se aplicó con otro contenido",
                        details={
                            "filename": filename,
                            "schema": schema,
                            "service": service,
                        },
                    )
                skipped.append(filename)
                continue

            async with conn.transaction():
                await conn.execute(
                    f"SET search_path TO {quote_identifier(schema)}, public"
                )
                await conn.execute(sql)
                await conn.execute(
                    """
                    INSERT INTO public.freya_schema_migrations
                        (schema_name, service, filename, checksum)
                    VALUES ($1, $2, $3, $4)
                    """,
                    schema,
                    service,
                    filename,
                    checksum,
                )
            applied.append(filename)

    return {"schema": schema, "applied": applied, "skipped": skipped}
