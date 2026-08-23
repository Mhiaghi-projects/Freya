"""Helpers de ejecución compartidos por los routers de gestor-db."""

from __future__ import annotations

import asyncpg
from freya_common import (
    BadRequest,
    Conflict,
    DependencyUnavailable,
    FreyaError,
    UnprocessableEntity,
)

_CONNECTION_ERRORS = (
    TimeoutError,
    asyncpg.exceptions.ConnectionDoesNotExistError,
    asyncpg.exceptions.TooManyConnectionsError,
)


def translate_pg_error(exc: asyncpg.PostgresError) -> FreyaError:
    """Traduce una excepción de asyncpg al formato de error de Freya.

    Caída de conexión → 503. Choque de unicidad → 409 (DUPLICATE_RESOURCE).
    Otra restricción violada → 422 (VALIDATION_ERROR). Cualquier otra cosa
    (típicamente SQL mal formado) → 400.
    """
    if isinstance(exc, _CONNECTION_ERRORS):
        return DependencyUnavailable(f"PostgreSQL no responde: {exc}")

    # Nunca el mensaje crudo: el DETAIL de Postgres para una violación de
    # unicidad incluye el valor exacto que chocó (p.ej. un email), y ese
    # valor puede no ser del propio llamante — no debe salir en una
    # respuesta HTTP. El nombre de la restricción basta para actuar.
    if isinstance(exc, asyncpg.exceptions.UniqueViolationError):
        constraint = getattr(exc, "constraint_name", None)
        return Conflict(
            "ya existe un registro con esos valores únicos",
            details={"constraint": constraint} if constraint else None,
        )
    if isinstance(exc, asyncpg.exceptions.IntegrityConstraintViolationError):
        constraint = getattr(exc, "constraint_name", None)
        return UnprocessableEntity(
            "la base rechazó la operación: viola una restricción de integridad",
            details={"constraint": constraint} if constraint else None,
        )
    return BadRequest(f"error de PostgreSQL: {exc}")


def parse_rows_affected(status: str) -> int:
    """Extrae el contador de un status de asyncpg ("UPDATE 3", "INSERT 0 1")."""
    parts = status.split()
    if not parts:
        return 0
    try:
        return int(parts[-1])
    except ValueError:
        return 0
