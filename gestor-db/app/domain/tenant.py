"""Resolución de base de datos por tenant (docs/freya-api-contract.md §4,
§16.1).

Una base de datos por tenant, no por tenant+servicio: "fortuna" es la
base del tenant "fortuna"; "fortuna_staging" es una base con nombre
dentro del mismo tenant (§4.5) -- cada tenant es una base física de
Postgres real, no un schema compartiendo una base con los demás (pedido
explícito del usuario: aislamiento real, no sólo lógico). El "database"
del cuerpo tiene que pertenecer al tenant autenticado -- si no, es
TENANT_MISMATCH, nunca se deriva del cuerpo a ciegas.
"""

from __future__ import annotations

import re

from freya_common import BadRequest, TenantMismatch

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")


def validate_tenant(tenant: str) -> str:
    if not _IDENTIFIER.match(tenant):
        raise BadRequest(f"X-Tenant-Context inválido: {tenant!r}")
    return tenant


def resolve_database(tenant: str, requested_database: str | None) -> str:
    """Sin "database" en el cuerpo, es el propio tenant. Con uno, tiene
    que ser el tenant o "<tenant>_algo"."""
    validate_tenant(tenant)
    database = requested_database or tenant
    if database != tenant and not database.startswith(f"{tenant}_"):
        raise TenantMismatch(
            f"La base '{database}' no pertenece al tenant '{tenant}'",
            details={"database": database, "tenant": tenant},
        )
    if not _IDENTIFIER.match(database):
        raise BadRequest(f"database inválida: {database!r}")
    return database


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
