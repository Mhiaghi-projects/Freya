"""Resolución de schema por tenant (docs/freya-api-contract.md §4, §16.1).

Un schema por tenant, no por tenant+servicio: "fortuna" es el schema del
tenant "fortuna"; "fortuna_staging" es un schema con nombre dentro del mismo
tenant (§4.5). El "schema" del cuerpo tiene que pertenecer al tenant
autenticado — si no, es TENANT_MISMATCH, nunca se deriva del cuerpo a ciegas.
"""

from __future__ import annotations

import re

from freya_common import BadRequest, TenantMismatch

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")


def validate_tenant(tenant: str) -> str:
    if not _IDENTIFIER.match(tenant):
        raise BadRequest(f"X-Tenant-Context inválido: {tenant!r}")
    return tenant


def resolve_schema(tenant: str, requested_schema: str | None) -> str:
    """Sin "schema" en el cuerpo, es el propio tenant. Con uno, tiene que
    ser el tenant o "<tenant>_algo"."""
    validate_tenant(tenant)
    schema = requested_schema or tenant
    if schema != tenant and not schema.startswith(f"{tenant}_"):
        raise TenantMismatch(
            f"El schema '{schema}' no pertenece al tenant '{tenant}'",
            details={"schema": schema, "tenant": tenant},
        )
    if not _IDENTIFIER.match(schema):
        raise BadRequest(f"schema inválido: {schema!r}")
    return schema


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
