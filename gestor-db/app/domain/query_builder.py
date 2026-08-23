"""Traduce el DSL estructurado de /query, /mutate y /transaction a SQL
parametrizado (docs/freya-api-contract.md §4).

Regla dura: nunca se interpola un VALOR en el texto SQL, sólo identificadores
(schema, tabla, columna) — y sólo tras validarlos contra un patrón estricto.
Los valores siempre van como parámetro ligado ($1, $2, ...).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from freya_common import BadRequest

_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")

# El DSL viaja en JSON: una fecha llega como texto ISO-8601, nunca como
# datetime.datetime/datetime.date. asyncpg exige el tipo Python real para
# columnas timestamptz/date -- no basta con un $N::timestamptz en el SQL
# generado, porque el tipo de la columna real no se conoce aquí (el builder
# es agnóstico del esquema). Se detecta el patrón y se convierte antes de
# ligar el parámetro. El de fecha (sin hora) tiene que probarse DESPUÉS del
# de fecha+hora -- "2026-08-22T10:00:00" también empieza como
# "2026-08-22", así que si el orden fuera al revés nunca llegaría a
# intentar el datetime completo.
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _coerce(value: Any) -> Any:
    if isinstance(value, str) and _ISO_DATETIME.match(value):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if isinstance(value, str) and _ISO_DATE.match(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return value
    return value


def _bind(params: list[Any], value: Any) -> str:
    """Añade un valor a params (convertido si hace falta) y devuelve su
    marcador $N."""
    params.append(_coerce(value))
    return f"${len(params)}"


_COMPARISON_OPERATORS = {
    "eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "like": "LIKE",
}


def quote(identifier: str) -> str:
    if not _IDENTIFIER.match(identifier):
        raise BadRequest(f"identificador inválido: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def _where_clause(where: dict[str, Any] | None, params: list[Any]) -> str:
    if not where:
        return ""
    clauses: list[str] = []
    for field, condition in where.items():
        column = quote(field)
        if isinstance(condition, dict):
            for op, value in condition.items():
                if op in ("in", "nin"):
                    if not isinstance(value, list) or not value:
                        raise BadRequest(f"'{op}' necesita una lista no vacía")
                    placeholders = [_bind(params, item) for item in value]
                    keyword = "IN" if op == "in" else "NOT IN"
                    clauses.append(f"{column} {keyword} ({', '.join(placeholders)})")
                elif op == "is_null":
                    clauses.append(f"{column} IS {'NULL' if value else 'NOT NULL'}")
                elif op == "between":
                    if not isinstance(value, list) or len(value) != 2:
                        raise BadRequest("'between' necesita un array de 2 valores")
                    low = _bind(params, value[0])
                    high = _bind(params, value[1])
                    clauses.append(f"{column} BETWEEN {low} AND {high}")
                elif op in _COMPARISON_OPERATORS:
                    placeholder = _bind(params, value)
                    operator = _COMPARISON_OPERATORS[op]
                    clauses.append(f"{column} {operator} {placeholder}")
                else:
                    raise BadRequest(f"operador '{op}' no soportado")
        else:
            placeholder = _bind(params, condition)
            clauses.append(f"{column} = {placeholder}")
    return " AND ".join(clauses)


def build_select(
    *,
    table: str,
    select: list[str] | None,
    where: dict[str, Any] | None,
    order_by: list[dict[str, str]] | None,
    limit: int,
    offset: int,
) -> tuple[str, list[Any]]:
    columns = ", ".join(quote(c) for c in select) if select else "*"
    sql = f"SELECT {columns} FROM {quote(table)}"
    params: list[Any] = []

    clause = _where_clause(where, params)
    if clause:
        sql += f" WHERE {clause}"

    if order_by:
        parts = []
        for item in order_by:
            direction = "DESC" if item.get("direction") == "desc" else "ASC"
            parts.append(f"{quote(item['field'])} {direction}")
        sql += " ORDER BY " + ", ".join(parts)

    sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
    return sql, params


def _set_clause(column: str, value: Any, params: list[Any]) -> str:
    quoted = quote(column)
    if isinstance(value, dict):
        if "increment" in value:
            placeholder = _bind(params, value["increment"])
            return f"{quoted} = {quoted} + {placeholder}"
        if "decrement" in value:
            placeholder = _bind(params, value["decrement"])
            return f"{quoted} = {quoted} - {placeholder}"
        raise BadRequest(f"operador de actualización no soportado para '{column}'")
    placeholder = _bind(params, value)
    return f"{quoted} = {placeholder}"


def build_insert(
    *,
    table: str,
    data: dict[str, Any] | list[dict[str, Any]] | None,
    returning: list[str] | None,
) -> tuple[str, list[Any]]:
    if not data:
        raise BadRequest("'data' es obligatorio en insert")
    rows = data if isinstance(data, list) else [data]
    if not rows:
        raise BadRequest("'data' está vacío")
    columns = list(rows[0].keys())
    for row in rows:
        if list(row.keys()) != columns:
            raise BadRequest(
                "todas las filas de un insert masivo deben tener las mismas columnas"
            )

    params: list[Any] = []
    value_groups = []
    for row in rows:
        placeholders = [_bind(params, row[column]) for column in columns]
        value_groups.append(f"({', '.join(placeholders)})")

    sql = (
        f"INSERT INTO {quote(table)} ({', '.join(quote(c) for c in columns)}) "
        f"VALUES {', '.join(value_groups)}"
    )
    if returning:
        sql += " RETURNING " + ", ".join(quote(c) for c in returning)
    return sql, params


def build_update(
    *,
    table: str,
    where: dict[str, Any] | None,
    data: dict[str, Any] | list[dict[str, Any]] | None,
    returning: list[str] | None,
) -> tuple[str, list[Any]]:
    if not where:
        raise BadRequest("update sin 'where' no está permitido")
    if not data or isinstance(data, list):
        raise BadRequest("update necesita 'data' como objeto")

    params: list[Any] = []
    set_clauses = [_set_clause(column, value, params) for column, value in data.items()]
    sql = f"UPDATE {quote(table)} SET {', '.join(set_clauses)}"
    clause = _where_clause(where, params)
    sql += f" WHERE {clause}"
    if returning:
        sql += " RETURNING " + ", ".join(quote(c) for c in returning)
    return sql, params


def build_delete(*, table: str, where: dict[str, Any] | None) -> tuple[str, list[Any]]:
    if not where:
        raise BadRequest("delete sin 'where' no está permitido")
    params: list[Any] = []
    clause = _where_clause(where, params)
    sql = f"DELETE FROM {quote(table)} WHERE {clause}"
    return sql, params


def build_upsert(
    *,
    table: str,
    data: dict[str, Any] | list[dict[str, Any]] | None,
    conflict_target: list[str] | None,
    returning: list[str] | None,
) -> tuple[str, list[Any]]:
    if not conflict_target:
        raise BadRequest("upsert necesita 'conflict_target'")
    sql, params = build_insert(table=table, data=data, returning=None)

    rows = data if isinstance(data, list) else [data]
    columns = list(rows[0].keys())
    update_columns = [c for c in columns if c not in conflict_target]
    if not update_columns:
        raise BadRequest(
            "upsert necesita al menos una columna fuera de 'conflict_target'"
        )
    set_clause = ", ".join(f"{quote(c)} = EXCLUDED.{quote(c)}" for c in update_columns)

    sql += (
        f" ON CONFLICT ({', '.join(quote(c) for c in conflict_target)}) "
        f"DO UPDATE SET {set_clause}"
    )
    if returning:
        sql += " RETURNING " + ", ".join(quote(c) for c in returning)
    return sql, params
