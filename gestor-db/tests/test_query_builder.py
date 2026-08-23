"""DSL estructurado -> SQL parametrizado (docs/freya-api-contract.md §4). Sin
base: son funciones puras sobre el árbol del request."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from freya_common import BadRequest

from app.domain.query_builder import (
    build_delete,
    build_insert,
    build_select,
    build_update,
    build_upsert,
)


def test_select_simple() -> None:
    sql, params = build_select(
        table="transactions", select=["id", "amount"], where=None,
        order_by=None, limit=50, offset=0,
    )
    assert sql == 'SELECT "id", "amount" FROM "transactions" LIMIT 50 OFFSET 0'
    assert params == []


def test_select_con_operadores_en_where() -> None:
    sql, params = build_select(
        table="transactions", select=None,
        where={"status": "pending", "amount": {"gte": 1000}},
        order_by=[{"field": "created_at", "direction": "desc"}],
        limit=10, offset=0,
    )
    assert '"status" = $1' in sql
    assert '"amount" >= $2' in sql
    assert 'ORDER BY "created_at" DESC' in sql
    assert params == ["pending", 1000]


def test_select_operador_in() -> None:
    sql, params = build_select(
        table="t", select=None, where={"status": {"in": ["a", "b"]}},
        order_by=None, limit=50, offset=0,
    )
    assert '"status" IN ($1, $2)' in sql
    assert params == ["a", "b"]


def test_select_rechaza_identificador_invalido() -> None:
    with pytest.raises(BadRequest):
        build_select(
            table="t; DROP TABLE t", select=None, where=None,
            order_by=None, limit=50, offset=0,
        )


def test_insert_una_fila() -> None:
    sql, params = build_insert(
        table="transactions", data={"amount": 500, "status": "pending"},
        returning=["id"],
    )
    assert sql.startswith('INSERT INTO "transactions"')
    assert "RETURNING \"id\"" in sql
    assert params == [500, "pending"]


def test_insert_bulk_exige_mismas_columnas() -> None:
    with pytest.raises(BadRequest):
        build_insert(
            table="t", data=[{"a": 1}, {"b": 2}], returning=None,
        )


def test_update_exige_where() -> None:
    with pytest.raises(BadRequest):
        build_update(table="t", where=None, data={"status": "done"}, returning=None)


def test_update_con_incremento() -> None:
    sql, params = build_update(
        table="balances", where={"id": 1}, data={"amount": {"decrement": 500}},
        returning=None,
    )
    assert '"amount" = "amount" - $1' in sql
    assert 1 in params and 500 in params


def test_insert_convierte_datetime_iso_a_datetime() -> None:
    # Bug real: una columna timestamptz necesita un datetime.datetime de
    # verdad, no el string ISO que trae el JSON del DSL.
    _sql, params = build_insert(
        table="t", data={"created_at": "2026-08-22T10:00:00Z"}, returning=None
    )
    assert isinstance(params[0], datetime)


def test_insert_convierte_fecha_iso_a_date() -> None:
    # Mismo bug, pero para columnas "date" (sin hora): encontrado en vivo
    # construyendo gamification (gam_user_stats.last_activity_date) --
    # _ISO_DATETIME no matchea "2026-08-22" (sin hora), así que el string
    # llegaba a asyncpg tal cual y asyncpg lo rechazaba para una columna
    # date real ("'str' object has no attribute 'toordinal'").
    _sql, params = build_insert(
        table="t", data={"last_activity_date": "2026-08-22"}, returning=None
    )
    assert params[0] == date(2026, 8, 22)


def test_insert_no_convierte_texto_que_no_es_fecha() -> None:
    _sql, params = build_insert(table="t", data={"name": "2026-08-22 no es todo"}, returning=None)
    assert params[0] == "2026-08-22 no es todo"


def test_delete_exige_where() -> None:
    with pytest.raises(BadRequest):
        build_delete(table="t", where=None)


def test_upsert_exige_conflict_target() -> None:
    with pytest.raises(BadRequest):
        build_upsert(table="t", data={"id": 1}, conflict_target=None, returning=None)


def test_upsert_genera_on_conflict() -> None:
    sql, params = build_upsert(
        table="t", data={"id": 1, "count": 2}, conflict_target=["id"], returning=None,
    )
    assert "ON CONFLICT (\"id\") DO UPDATE SET" in sql
    assert '"count" = EXCLUDED."count"' in sql
    assert params == [1, 2]
