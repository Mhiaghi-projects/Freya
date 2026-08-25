"""Resolución de base de datos por tenant (docs/freya-api-contract.md §4, §16.1)."""

from __future__ import annotations

import pytest
from freya_common import BadRequest, TenantMismatch

from app.domain.tenant import resolve_database


def test_sin_database_explicita_usa_el_tenant() -> None:
    assert resolve_database("fortuna", None) == "fortuna"


def test_database_con_nombre_del_propio_tenant() -> None:
    assert resolve_database("fortuna", "fortuna_staging") == "fortuna_staging"


def test_database_de_otro_tenant_es_tenant_mismatch() -> None:
    with pytest.raises(TenantMismatch):
        resolve_database("fortuna", "potato")
    with pytest.raises(TenantMismatch):
        resolve_database("fortuna", "potato_staging")


def test_tenant_invalido_es_bad_request() -> None:
    with pytest.raises(BadRequest):
        resolve_database("Fortuna", None)
    with pytest.raises(BadRequest):
        resolve_database("fortuna; DROP DATABASE freya", None)
