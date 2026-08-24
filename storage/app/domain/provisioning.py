"""Aprovisiona un tenant nuevo para storage (pedido explícito del usuario:
automatizar la creación de un tenant, pero sólo aislamiento de datos -- sin
levantar ningún contenedor/servicio nuevo). Aplica las propias migraciones
de storage contra el schema del tenant (mismo mecanismo que
freya_common.MigrationRunner usa al arrancar, pero disparado on-demand
contra un tenant arbitrario en vez de sólo el propio al boot) y crea el
bucket compartido "project" de ese tenant."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from freya_common import FreyaError, ServiceClient, load_migrations

from app.domain.buckets import create_bucket

# Bucket compartido por tenant, visible a todo el que tenga write:storage
# en ese proyecto -- distinto del bucket "users" (personal, sólo vive en
# el tenant "freya", ver docs/DECISIONS.md).
PROJECT_BUCKET = "project"


async def provision_tenant(
    client: ServiceClient,
    tenant: str,
    *,
    migrations_dir: Path,
    default_max_versions: int,
    default_quota_bytes: int,
) -> dict[str, Any]:
    migrations = load_migrations(migrations_dir)
    await client.post(
        "/migrations",
        tenant=tenant,
        json={"schema": tenant, "migrations": migrations},
    )
    try:
        await create_bucket(
            client,
            tenant,
            bucket=PROJECT_BUCKET,
            versioning=False,
            encryption=False,
            max_versions=default_max_versions,
            quota_bytes=default_quota_bytes,
        )
    except FreyaError as exc:
        if exc.status_code != 409:
            raise
    return {"tenant": tenant, "bucket": PROJECT_BUCKET}
